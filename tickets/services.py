"""Reglas de negocio de los tickets (HU-06, HU-07, HU-08).

Cada acción valida el permiso del actor, la transición de estado, y deja rastro en el
historial del ticket, en las notificaciones y en la auditoría, todo dentro de una transacción.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from auditoria import services as auditoria
from core.cloudinary_service import ActivoInvalido, obtener_servicio
from core.permisos import (
    AUDITOR,
    JEFATURA,
    TECNICO_EXTERNO,
    TECNICO_INTERNO,
    TRABAJADOR,
    codigo_perfil,
)
from core.validators import ErrorValidacion
from inventario.selectors import equipos_visibles
from notificaciones.services import notificar, notificar_perfil
from tickets import estados
from tickets.models import DocumentoRespaldo, HistorialEstado, Material, Ticket
from tickets.validacion import normalizar_documentos, normalizar_materiales

# --------------------------------------------------------------------------- alcance


def tickets_visibles(usuario):
    base = Ticket.objects.select_related("equipo", "solicitante", "tecnico")
    codigo = codigo_perfil(usuario)
    if codigo == AUDITOR:
        return base
    if codigo == JEFATURA:
        if usuario.sucursal_id:
            return base.filter(
                Q(equipo__sucursal_id=usuario.sucursal_id) | Q(equipo__isnull=True, solicitante__sucursal_id=usuario.sucursal_id)
            )
        return base
    if codigo == TECNICO_INTERNO:
        return base.filter(Q(tecnico=usuario) | Q(solicitante=usuario))
    if codigo == TECNICO_EXTERNO:
        return base.filter(tecnico=usuario)
    if codigo == TRABAJADOR:
        return base.filter(solicitante=usuario)
    return base.none()


def tecnicos_elegibles(ticket: Ticket):
    from cuentas.models import Usuario

    internos = Usuario.objects.filter(perfil__codigo=TECNICO_INTERNO, is_active=True)
    externos = Usuario.objects.filter(perfil__codigo=TECNICO_EXTERNO, is_active=True)
    if ticket.equipo_id:
        internos = internos.filter(sucursal_id=ticket.equipo.sucursal_id)
        externos = externos.filter(equipos_asignados=ticket.equipo)
    else:
        if ticket.solicitante.sucursal_id:
            internos = internos.filter(sucursal_id=ticket.solicitante.sucursal_id)
        externos = externos.none()
    return Usuario.objects.filter(Q(pk__in=internos.values("pk")) | Q(pk__in=externos.values("pk"))).order_by("apellido")


# --------------------------------------------------------------------------- utilidades internas


def _exigir_permiso(actor, permiso: str, ticket: Ticket | None = None):
    if not actor.tiene_permiso(permiso):
        auditoria.registrar(
            actor, auditoria.ACCESO_DENEGADO, "ticket", ticket.pk if ticket else None, {"permiso": permiso}
        )
        raise PermissionDenied(f"Falta el permiso {permiso}.")


def _exigir_tecnico_asignado(actor, ticket: Ticket):
    _exigir_permiso(actor, "tickets.ejecutar", ticket)
    if ticket.tecnico_id != actor.pk:
        auditoria.registrar(actor, auditoria.ACCESO_DENEGADO, "ticket", ticket.pk, {"motivo": "no es el técnico asignado"})
        raise PermissionDenied("Este ticket está asignado a otro técnico.")


def _cambiar_estado(ticket: Ticket, nuevo: str, actor, observacion: str = "", request=None) -> None:
    anterior = ticket.estado
    try:
        estados.validar_transicion(anterior, nuevo)
    except estados.TransicionInvalida as exc:
        raise ValidationError(str(exc)) from exc
    if nuevo in estados.EXIGEN_MOTIVO and not observacion.strip():
        raise ValidationError("Debes indicar el motivo.")
    ticket.estado = nuevo
    HistorialEstado.objects.create(ticket=ticket, estado=nuevo, observacion=observacion[:300], usuario=actor)
    auditoria.registrar(
        actor, auditoria.TICKET_CAMBIO_ESTADO, "ticket", ticket.pk, {"de": anterior, "a": nuevo, "obs": observacion[:100]}, request
    )


def _url(ticket: Ticket) -> str:
    return reverse("tickets:detalle", args=[ticket.pk])


# --------------------------------------------------------------------------- acciones


@transaction.atomic
def crear_ticket(solicitante, tipo: str, descripcion: str, equipo=None, request=None) -> Ticket:
    """HU-06: queda en Pendiente de aprobación y avisa a la jefatura."""
    _exigir_permiso(solicitante, "tickets.crear")
    if equipo is not None and not equipos_visibles(solicitante).filter(pk=equipo.pk).exists():
        auditoria.registrar(solicitante, auditoria.ACCESO_DENEGADO, "equipo", equipo.pk, {"via": "ticket"}, request)
        raise PermissionDenied("No puedes reportar fallas de un equipo que no puedes ver.")
    if not descripcion.strip():
        raise ValidationError("Describe la falla.")
    ticket = Ticket.objects.create(solicitante=solicitante, tipo=tipo, descripcion=descripcion.strip(), equipo=equipo)
    HistorialEstado.objects.create(ticket=ticket, estado=estados.PENDIENTE, observacion="Ticket creado", usuario=solicitante)
    auditoria.registrar(solicitante, auditoria.TICKET_CAMBIO_ESTADO, "ticket", ticket.pk, {"de": "", "a": estados.PENDIENTE}, request)
    sucursal = equipo.sucursal_id if equipo else solicitante.sucursal_id
    notificar_perfil(
        JEFATURA, f"Ticket {ticket.numero} por aprobar: {descripcion.strip()[:80]}", _url(ticket), f"ticket-{ticket.pk}-nuevo", sucursal
    )
    return ticket


@transaction.atomic
def aprobar(ticket: Ticket, actor, tecnico, request=None) -> None:
    """HU-07: aprueba y asigna a un técnico; la asignación le avisa."""
    _exigir_permiso(actor, "tickets.aprobar", ticket)
    if not tecnicos_elegibles(ticket).filter(pk=tecnico.pk).exists():
        raise ValidationError("El técnico elegido no corresponde a este equipo o sucursal.")
    _cambiar_estado(ticket, estados.APROBADO, actor, f"Asignado a {tecnico}", request)
    ticket.tecnico = tecnico
    ticket.save(update_fields=["estado", "tecnico"])
    notificar([tecnico], f"Se te asignó el ticket {ticket.numero}.", _url(ticket), f"ticket-{ticket.pk}-asignado-{tecnico.pk}")
    notificar([ticket.solicitante], f"Tu ticket {ticket.numero} fue aprobado.", _url(ticket), f"ticket-{ticket.pk}-aprobado")


@transaction.atomic
def rechazar(ticket: Ticket, actor, motivo: str, request=None) -> None:
    _exigir_permiso(actor, "tickets.aprobar", ticket)
    _cambiar_estado(ticket, estados.RECHAZADO, actor, motivo, request)
    ticket.motivo_rechazo = motivo.strip()[:300]
    ticket.save(update_fields=["estado", "motivo_rechazo"])
    notificar([ticket.solicitante], f"Tu ticket {ticket.numero} fue rechazado: {ticket.motivo_rechazo[:100]}", _url(ticket), f"ticket-{ticket.pk}-rechazado")


@transaction.atomic
def iniciar(ticket: Ticket, actor, request=None) -> None:
    _exigir_tecnico_asignado(actor, ticket)
    _cambiar_estado(ticket, estados.EN_EJECUCION, actor, "Trabajo iniciado", request)
    ticket.inicio_trabajo = ticket.inicio_trabajo or timezone.now()
    ticket.save(update_fields=["estado", "inicio_trabajo"])


@transaction.atomic
def realizar(ticket: Ticket, actor, materiales_bruto, documentos_bruto, observacion: str = "", request=None) -> None:
    """HU-08: cierra el trabajo con inicio, término, materiales y documentos de respaldo."""
    _exigir_tecnico_asignado(actor, ticket)
    nube = obtener_servicio()
    try:
        materiales = normalizar_materiales(materiales_bruto)
        documentos = normalizar_documentos(documentos_bruto, nube.prefijo_url)
    except ErrorValidacion as exc:
        raise ValidationError(exc.errores) from exc

    verificados = []
    errores = []
    for pos, doc in enumerate(documentos, start=1):
        try:
            real = nube.verificar_activo(doc["public_id"], "foto")
        except ActivoInvalido as exc:
            errores.append(f"Documento {pos}: {exc}")
            continue
        verificados.append({**doc, "url": real.url})
    if errores:
        raise ValidationError(errores)

    _cambiar_estado(ticket, estados.REALIZADO, actor, observacion or "Trabajo realizado", request)
    ticket.termino_trabajo = timezone.now()
    ticket.save(update_fields=["estado", "termino_trabajo"])
    Material.objects.bulk_create([Material(ticket=ticket, **m) for m in materiales])
    DocumentoRespaldo.objects.bulk_create(
        [
            DocumentoRespaldo(
                ticket=ticket, tipo=d["tipo"], numero=d["numero"], proveedor=d["proveedor"], monto=d["monto"], url_foto=d["url"]
            )
            for d in verificados
        ]
    )
    notificar_perfil(
        JEFATURA,
        f"Ticket {ticket.numero} realizado: revisa y cierra.",
        _url(ticket),
        f"ticket-{ticket.pk}-realizado-{ticket.historial.count()}",
        ticket.equipo.sucursal_id if ticket.equipo_id else None,
    )


@transaction.atomic
def cerrar(ticket: Ticket, actor, request=None) -> None:
    _exigir_permiso(actor, "tickets.cerrar", ticket)
    _cambiar_estado(ticket, estados.CERRADO, actor, "Revisado y cerrado", request)
    ticket.save(update_fields=["estado"])
    notificar([ticket.tecnico, ticket.solicitante], f"El ticket {ticket.numero} fue cerrado.", _url(ticket), f"ticket-{ticket.pk}-cerrado")


@transaction.atomic
def devolver(ticket: Ticket, actor, observacion: str, request=None) -> None:
    """La jefatura devuelve el ticket al técnico con observaciones."""
    _exigir_permiso(actor, "tickets.cerrar", ticket)
    if not observacion.strip():
        raise ValidationError("Indica qué debe corregir el técnico.")
    _cambiar_estado(ticket, estados.EN_EJECUCION, actor, f"Devuelto: {observacion}", request)
    ticket.termino_trabajo = None
    ticket.save(update_fields=["estado", "termino_trabajo"])
    notificar(
        [ticket.tecnico],
        f"El ticket {ticket.numero} fue devuelto con observaciones.",
        _url(ticket),
        f"ticket-{ticket.pk}-devuelto-{ticket.historial.count()}",
    )
