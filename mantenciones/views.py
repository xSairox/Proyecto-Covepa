import logging
from datetime import datetime, time

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView

from auditoria import services as auditoria
from core.mongo import obtener_repo
from core.permisos import (
    AUDITOR,
    JEFATURA,
    TECNICO_EXTERNO,
    TECNICO_INTERNO,
    PerfilRequeridoMixin,
    perfil_requerido,
)
from core.validators import TIPOS_MEDIA, ErrorValidacion
from cuentas.models import Usuario
from inventario.selectors import equipos_visibles
from mantenciones.forms import FormularioPlan, FormularioPlantilla
from mantenciones.models import PlanMantencion, Plantilla, RegistroMantencion
from mantenciones.selectors import registros_visibles

TECNICOS = (TECNICO_INTERNO, TECNICO_EXTERNO)
logger = logging.getLogger("covepa")


# --------------------------------------------------------------------------- técnico en terreno (PWA)


@perfil_requerido(*TECNICOS)
def inicio_tecnico(request):
    """Pantalla de inicio del técnico. Se dibuja en el navegador con los datos guardados para uso sin conexión."""
    return render(request, "mantenciones/inicio.html")


@perfil_requerido(*TECNICOS)
def registrar(request):
    """Formulario de mantención: carga la plantilla del equipo desde el dispositivo (HU-04, HU-05)."""
    return render(request, "mantenciones/registrar.html")


# --------------------------------------------------------------------------- historial


class HistorialLista(PerfilRequeridoMixin, ListView):
    perfiles = (JEFATURA, TECNICO_INTERNO, AUDITOR)
    template_name = "mantenciones/historial.html"
    context_object_name = "registros"
    paginate_by = 30

    def get_queryset(self):
        qs = registros_visibles(self.request.user)
        g = self.request.GET
        if g.get("equipo"):
            qs = qs.filter(equipo__codigo__icontains=g["equipo"].strip())
        if g.get("tecnico", "").isdigit():
            qs = qs.filter(tecnico_id=int(g["tecnico"]))
        zona = timezone.get_current_timezone()
        for clave, operador, hora in (("desde", "gte", time.min), ("hasta", "lte", time.max)):
            try:
                dia = datetime.strptime(g.get(clave, ""), "%Y-%m-%d").date()
            except ValueError:
                continue
            qs = qs.filter(**{f"inicio__{operador}": timezone.make_aware(datetime.combine(dia, hora), zona)})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Solo técnicos con registros que este usuario puede ver (no expone personal de otras sucursales)
        visibles = registros_visibles(self.request.user).values("tecnico_id")
        ctx["tecnicos"] = Usuario.objects.filter(pk__in=visibles).order_by("apellido", "nombre")
        ctx["filtros"] = self.request.GET
        return ctx


@perfil_requerido(JEFATURA, TECNICO_INTERNO, TECNICO_EXTERNO, AUDITOR)
def registro_detalle(request, pk):
    registro = get_object_or_404(RegistroMantencion.objects.select_related("equipo", "tecnico", "plantilla", "plan"), pk=pk)
    if not registros_visibles(request.user).filter(pk=pk).exists():
        auditoria.registrar(request.user, auditoria.ACCESO_DENEGADO, "registro_mantencion", pk, {"ruta": request.path}, request)
        raise PermissionDenied("No tienes acceso a este registro.")

    repo = obtener_repo()
    documento = repo.obtener_formulario(str(registro.pk))
    version = registro.plantilla.version(registro.version_plantilla)
    filas, evidencias = [], []
    if documento and version:
        respuestas = documento.get("respuestas", {})
        for campo in version["campos"]:
            if campo["tipo"] in TIPOS_MEDIA:
                continue
            valor = respuestas.get(campo["clave"])
            if isinstance(valor, bool):
                valor = "Sí" if valor else "No"
            elif valor is None:
                valor = "—"
            elif campo.get("unidad"):
                valor = f"{valor} {campo['unidad']}"
            filas.append({"etiqueta": campo["etiqueta"], "valor": valor})
        etiquetas = {c["clave"]: c["etiqueta"] for c in version["campos"]}
        evidencias = [{**e, "etiqueta": etiquetas.get(e["campo"], e["campo"])} for e in documento.get("evidencias", [])]
    return render(
        request,
        "mantenciones/registro_detalle.html",
        {"registro": registro, "documento": documento, "filas": filas, "evidencias": evidencias},
    )


# --------------------------------------------------------------------------- plantillas (HU-03)


@perfil_requerido(JEFATURA)
def plantillas_lista(request):
    return render(request, "mantenciones/plantillas_lista.html", {"plantillas": Plantilla.objects.select_related("categoria")})


@perfil_requerido(JEFATURA)
def plantilla_form(request, pk=None):
    plantilla = get_object_or_404(Plantilla, pk=pk) if pk else None
    form = FormularioPlantilla(request.POST or None, instance=plantilla)
    campos_iniciales = []
    versiones = []
    if plantilla:
        actual = plantilla.version()
        campos_iniciales = actual["campos"] if actual else []
        versiones = plantilla.versiones()
    if request.method == "POST" and form.is_valid():
        campos = form.cleaned_data["campos_json"]
        try:
            # Si MongoDB falla, la plantilla tampoco queda a medias en PostgreSQL
            with transaction.atomic():
                guardada = form.save()
                actual = guardada.version()
                cambio = actual is None or actual["campos"] != campos
                doc = guardada.publicar_version(campos) if cambio else None
        except ErrorValidacion as exc:
            for mensaje in exc.errores:
                form.add_error(None, mensaje)
        except Exception:  # noqa: BLE001 - p. ej. MongoDB sin conexión
            logger.exception("No se pudo publicar la plantilla")
            form.add_error(None, "No pudimos guardar la plantilla: la base de documentos no respondió. Inténtalo de nuevo.")
        else:
            if doc:
                auditoria.registrar(
                    request.user, auditoria.PLANTILLA_PUBLICADA, "plantilla", guardada.pk, {"version": doc["numero"]}, request
                )
                messages.success(request, f"Plantilla guardada. Versión {doc['numero']} publicada.")
            else:
                messages.success(request, "Plantilla guardada. Los campos no cambiaron: no se creó una versión nueva.")
            return redirect("mantenciones:plantillas")
    if request.method == "POST" and form.cleaned_data.get("campos_json") is not None:
        campos_iniciales = form.cleaned_data["campos_json"]
    return render(
        request,
        "mantenciones/plantilla_form.html",
        {"form": form, "plantilla": plantilla, "campos_iniciales": campos_iniciales, "versiones": versiones},
    )


# --------------------------------------------------------------------------- planes de mantención


@perfil_requerido(JEFATURA)
def planes_lista(request):
    planes = PlanMantencion.objects.filter(equipo__in=equipos_visibles(request.user).values("pk")).select_related(
        "equipo", "plantilla"
    )
    if request.GET.get("equipo"):
        planes = planes.filter(equipo__codigo__icontains=request.GET["equipo"].strip())
    return render(request, "mantenciones/planes_lista.html", {"planes": planes, "filtros": request.GET})


@perfil_requerido(JEFATURA)
def plan_form(request, pk=None):
    plan = None
    if pk:
        plan = get_object_or_404(PlanMantencion.objects.filter(equipo__in=equipos_visibles(request.user).values("pk")), pk=pk)
    form = FormularioPlan(request.POST or None, instance=plan, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        auditoria.registrar(request.user, auditoria.PLAN_GUARDADO, "plan_mantencion", plan.pk, {"cada_dias": plan.frecuencia_dias}, request)
        messages.success(request, "Plan de mantención guardado.")
        return redirect("mantenciones:planes")
    return render(request, "mantenciones/plan_form.html", {"form": form, "plan": plan})
