"""Sincronización de formularios de mantención (HU-04 y HU-05).

El celular genera un documento JSON con un UUID. Aquí se valida, se descartan duplicados y se
guarda en las DOS bases: el formulario completo en MongoDB y los datos para filtrar en PostgreSQL.

Como no existe una transacción que abarque ambas bases, el orden es:
  1. MongoDB (inserción idempotente por _id).
  2. PostgreSQL dentro de una transacción.
  3. Si PostgreSQL falla, se compensa borrando el documento recién insertado en MongoDB.
Un reenvío por mala señal reconoce el UUID y no duplica nada.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from auditoria import services as auditoria
from core.cloudinary_service import ActivoInvalido, obtener_servicio
from core.mongo import obtener_repo
from core.validators import ErrorValidacion, validar_formulario
from inventario.models import Equipo
from inventario.selectors import equipos_visibles
from mantenciones.models import Plantilla, PlanMantencion, RegistroMantencion

logger = logging.getLogger("covepa.sincronizacion")


class SincronizacionError(Exception):
    """Error de negocio con el código HTTP que corresponde y la lista de mensajes para el cliente."""

    def __init__(self, http: int, errores: list[str]):
        self.http = http
        self.errores = errores
        super().__init__("; ".join(errores))


@dataclass
class ResultadoSync:
    registro: RegistroMantencion
    creado: bool


def _aware(valor):
    if timezone.is_naive(valor):
        return timezone.make_aware(valor, timezone.get_current_timezone())
    return valor


def _resolver_equipo(payload: dict, usuario, request) -> Equipo:
    datos = payload.get("equipo")
    codigo = datos.get("codigo") if isinstance(datos, dict) else None
    if not isinstance(codigo, str):
        raise SincronizacionError(400, ["Falta equipo.codigo en el documento."])
    codigo = codigo.strip().upper()
    existente = Equipo.objects.filter(codigo=codigo).first()
    if existente is None:
        raise SincronizacionError(400, [f"El equipo {codigo} no existe."])
    equipo = equipos_visibles(usuario).filter(pk=existente.pk).first()
    if equipo is None:  # existe, pero no está asignado a este usuario (OWASP A01)
        auditoria.registrar(
            usuario, auditoria.ACCESO_DENEGADO, "equipo", existente.pk, {"codigo": codigo, "via": "sincronizacion"}, request
        )
        raise SincronizacionError(403, [f"No tienes acceso al equipo {codigo}."])
    if equipo.esta_de_baja:
        raise SincronizacionError(400, [f"El equipo {codigo} está dado de baja."])
    return equipo


def _resolver_plantilla(payload: dict, equipo: Equipo) -> tuple[Plantilla, int, dict]:
    datos = payload.get("plantilla")
    if not isinstance(datos, dict):
        raise SincronizacionError(400, ["Falta el objeto 'plantilla' (id o nombre, y version)."])
    numero = datos.get("version")
    if not isinstance(numero, int) or isinstance(numero, bool) or numero < 1:
        raise SincronizacionError(400, ["plantilla.version debe ser un número entero positivo."])
    consulta = Plantilla.objects.filter(categoria=equipo.categoria)
    if datos.get("id") is not None:
        plantilla = consulta.filter(pk=datos["id"]).first() if isinstance(datos["id"], int) else None
    else:
        plantilla = consulta.filter(nombre=datos.get("nombre")).first()
    if plantilla is None:
        raise SincronizacionError(400, ["La plantilla no existe o no corresponde a la categoría del equipo."])
    version = obtener_repo().obtener_version(plantilla.pk, numero)
    if version is None:
        raise SincronizacionError(400, [f"La versión {numero} de la plantilla no existe."])
    return plantilla, numero, version


def _verificar_evidencias(evidencias: list[dict]) -> list[dict]:
    """Comprueba en Cloudinary que cada archivo exista, esté en la carpeta autorizada y cumpla los límites.

    Los datos (URL, peso, duración) se reemplazan por los que informa Cloudinary: no se confía en el celular.
    """
    nube = obtener_servicio()
    errores: list[str] = []
    verificadas: list[dict] = []
    for pos, ev in enumerate(evidencias, start=1):
        if not ev.get("public_id"):
            errores.append(f"Evidencia {pos}: falta el identificador del archivo (public_id).")
            continue
        try:
            real = nube.verificar_activo(ev["public_id"], ev["tipo"])
        except ActivoInvalido as exc:
            errores.append(f"Evidencia {pos} ({ev['campo']}): {exc}")
            if "supera" in str(exc) or "dura más" in str(exc):  # archivo fuera de límites: no se conserva
                try:
                    nube.eliminar(ev["public_id"], ev["tipo"])
                except Exception:  # noqa: BLE001
                    logger.warning("No se pudo eliminar %s de Cloudinary", ev["public_id"])
            continue
        verificadas.append({**ev, "url": real.url, "peso_kb": real.peso_kb, "duracion_seg": real.duracion_seg})
    if errores:
        raise SincronizacionError(400, errores)
    return verificadas


def sincronizar_formulario(payload, usuario, request=None) -> ResultadoSync:
    """Valida y guarda un formulario. Lanza SincronizacionError con el HTTP adecuado si no corresponde."""
    politicas = settings.POLITICAS
    repo = obtener_repo()

    if not isinstance(payload, dict):
        raise SincronizacionError(400, ["El cuerpo debe ser un objeto JSON."])

    # 1. Duplicado: mismo UUID ya sincronizado -> no se vuelve a guardar
    try:
        id_doc = uuid.UUID(str(payload.get("_id")))
    except ValueError:
        id_doc = None
    if id_doc is not None:
        previo = RegistroMantencion.objects.filter(pk=id_doc).first()
        if previo is not None:
            if previo.tecnico_id != usuario.pk:
                auditoria.registrar(usuario, auditoria.ACCESO_DENEGADO, "registro_mantencion", id_doc, {"motivo": "uuid ajeno"}, request)
                raise SincronizacionError(409, ["El identificador del documento ya pertenece a otro registro."])
            auditoria.registrar(usuario, auditoria.MANTENCION_DUPLICADA, "registro_mantencion", id_doc, request=request)
            return ResultadoSync(previo, creado=False)

    # 2. A quién pertenece y a qué equipo
    if payload.get("tecnico_id") is None:
        raise SincronizacionError(400, ["Falta tecnico_id en el documento."])
    if payload.get("tecnico_id") != usuario.pk:
        raise SincronizacionError(403, ["El formulario pertenece a otro técnico."])
    equipo = _resolver_equipo(payload, usuario, request)
    plantilla, numero_version, version = _resolver_plantilla(payload, equipo)

    plan = None
    if payload.get("plan_id") is not None:
        plan = PlanMantencion.objects.filter(pk=payload["plan_id"], equipo=equipo, activo=True).first() if isinstance(
            payload["plan_id"], int
        ) else None
        if plan is None:
            raise SincronizacionError(400, ["El plan de mantención no existe, está inactivo o es de otro equipo."])

    # 3. Estructura, tipos y rangos
    nube = obtener_servicio()
    try:
        limpio = validar_formulario(
            payload,
            version["campos"],
            ahora=timezone.now(),
            video_max_seg=politicas["VIDEO_MAX_SEG"],
            prefijo_url=nube.prefijo_url,
        )
    except ErrorValidacion as exc:
        auditoria.registrar(
            usuario,
            auditoria.MANTENCION_RECHAZADA,
            "registro_mantencion",
            payload.get("_id"),
            {"errores": exc.errores[:10], "equipo": equipo.codigo},
            request,
        )
        raise SincronizacionError(400, exc.errores) from exc

    # 4. Archivos en Cloudinary
    try:
        evidencias = _verificar_evidencias(limpio["evidencias"])
    except SincronizacionError as exc:
        auditoria.registrar(
            usuario, auditoria.MANTENCION_RECHAZADA, "registro_mantencion", payload.get("_id"), {"errores": exc.errores[:10]}, request
        )
        raise

    inicio, termino = _aware(limpio["inicio"]), _aware(limpio["termino"])
    documento = {
        "_id": limpio["id"],
        "equipo": {"codigo": equipo.codigo, "categoria": equipo.categoria.nombre},
        "sucursal": equipo.sucursal.nombre,
        "plantilla": {"id": plantilla.pk, "nombre": plantilla.nombre, "version": numero_version},
        "tecnico_id": usuario.pk,
        "inicio": inicio,
        "termino": termino,
        "respuestas": limpio["respuestas"],
        "evidencias": evidencias,
        "origen": limpio["origen"],
        "estado": "sincronizado",
        "plan_id": plan.pk if plan else None,
        "recibido_en": timezone.now(),
    }

    # 5. MongoDB primero (idempotente por _id)
    insertado = repo.insertar_formulario(documento)
    if not insertado:
        existente = repo.obtener_formulario(documento["_id"])
        if existente and existente.get("tecnico_id") != usuario.pk:
            raise SincronizacionError(409, ["El identificador del documento ya está en uso."])
        # Mismo técnico: quedó un documento de un intento anterior que falló en PostgreSQL. Se completa ahora.

    # 6. PostgreSQL en una transacción
    try:
        with transaction.atomic():
            registro = RegistroMantencion.objects.create(
                id=uuid.UUID(limpio["id"]),
                equipo=equipo,
                tecnico=usuario,
                plantilla=plantilla,
                version_plantilla=numero_version,
                plan=plan,
                inicio=inicio,
                termino=termino,
                estado_sync=RegistroMantencion.SINCRONIZADO,
                origen=limpio["origen"],
            )
            if plan is not None:
                fecha = timezone.localtime(termino).date()
                if plan.ultima_fecha is None or fecha > plan.ultima_fecha:
                    plan.ultima_fecha = fecha
                    plan.save(update_fields=["ultima_fecha"])
    except IntegrityError:
        # Dos envíos simultáneos del mismo UUID: el otro ganó, este es un duplicado.
        previo = RegistroMantencion.objects.filter(pk=id_doc).first()
        if previo is not None and previo.tecnico_id == usuario.pk:
            return ResultadoSync(previo, creado=False)
        if insertado:
            repo.eliminar_formulario(documento["_id"])
        raise
    except Exception:
        if insertado:  # compensación: evita un formulario huérfano en MongoDB
            try:
                repo.eliminar_formulario(documento["_id"])
            except Exception:  # noqa: BLE001
                logger.exception("Documento huérfano en MongoDB: %s", documento["_id"])
        raise

    auditoria.registrar(
        usuario,
        auditoria.MANTENCION_SINCRONIZADA,
        "registro_mantencion",
        registro.pk,
        {"equipo": equipo.codigo, "origen": limpio["origen"], "evidencias": len(evidencias)},
        request,
    )
    return ResultadoSync(registro, creado=True)


def construir_paquete(usuario) -> dict:
    """Datos que el celular guarda para trabajar sin conexión: equipos, plantillas vigentes y pendientes."""
    from datetime import timedelta

    from inventario.models import Equipo
    from mantenciones.selectors import planes_pendientes
    from tickets import estados
    from tickets.models import Ticket

    hoy = timezone.localdate()
    equipos = equipos_visibles(usuario).exclude(estado=Equipo.BAJA)
    lista_equipos = list(equipos)
    categorias = {e.categoria_id for e in lista_equipos}
    plantillas = Plantilla.objects.filter(categoria_id__in=categorias, activa=True, version_actual__gt=0)

    repo = obtener_repo()
    plantillas_json: dict[str, dict] = {}
    por_categoria: dict[int, list[int]] = {}
    for p in plantillas:
        version = repo.obtener_version(p.pk, p.version_actual)
        if version is None:
            continue
        plantillas_json[str(p.pk)] = {
            "id": p.pk,
            "nombre": p.nombre,
            "categoria_id": p.categoria_id,
            "version": version["numero"],
            "campos": version["campos"],
        }
        por_categoria.setdefault(p.categoria_id, []).append(p.pk)

    pendientes = []
    for plan in planes_pendientes(equipos, dias_adelante=7):
        pendientes.append(
            {
                "plan_id": plan.pk,
                "equipo_id": plan.equipo_id,
                "equipo_codigo": plan.equipo.codigo,
                "actividad": plan.actividad,
                "plantilla_id": plan.plantilla_id,
                "proxima_fecha": plan.proxima_fecha().isoformat(),
                "vencida": plan.proxima_fecha() < hoy,
            }
        )

    tickets = Ticket.objects.filter(tecnico=usuario).exclude(estado__in=estados.ESTADOS_FINALES).select_related("equipo")[:20]
    recientes = (
        RegistroMantencion.objects.filter(tecnico=usuario, inicio__gte=timezone.now() - timedelta(days=30))
        .select_related("equipo")
        .order_by("-inicio")[:10]
    )
    return {
        "generado_en": timezone.now().isoformat(),
        "usuario": {"id": usuario.pk, "nombre": str(usuario), "perfil": usuario.perfil.codigo},
        "equipos": [
            {
                "id": e.pk,
                "codigo": e.codigo,
                "nombre": e.nombre,
                "categoria_id": e.categoria_id,
                "categoria": e.categoria.nombre,
                "sucursal": e.sucursal.nombre,
                "plantillas": por_categoria.get(e.categoria_id, []),
            }
            for e in lista_equipos
        ],
        "plantillas": plantillas_json,
        "pendientes": pendientes,
        "tickets": [
            {
                "id": t.pk,
                "numero": t.numero,
                "estado": t.estado,
                "descripcion": t.descripcion[:140],
                "equipo": t.equipo.codigo if t.equipo_id else "",
                "url": f"/tickets/{t.pk}/",
            }
            for t in tickets
        ],
        "recientes": [
            {"id": str(r.pk), "equipo": r.equipo.codigo, "inicio": r.inicio.isoformat()} for r in recientes
        ],
        "limites": {
            "video_max_seg": settings.POLITICAS["VIDEO_MAX_SEG"],
            "foto_max_mb": settings.POLITICAS["FOTO_MAX_MB"],
            "video_max_mb": settings.POLITICAS["VIDEO_MAX_MB"],
        },
    }
