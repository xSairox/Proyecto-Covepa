from datetime import datetime, time

from django.utils import timezone
from django.views.generic import ListView

from auditoria.models import Auditoria
from core.permisos import AUDITOR, JEFATURA, PerfilRequeridoMixin


class AuditoriaLista(PerfilRequeridoMixin, ListView):
    """Consulta de auditoría, de solo lectura, con filtros."""

    perfiles = (AUDITOR, JEFATURA)
    model = Auditoria
    template_name = "auditoria/lista.html"
    paginate_by = 40
    context_object_name = "eventos"

    def get_queryset(self):
        qs = Auditoria.objects.select_related("usuario")
        g = self.request.GET
        if g.get("accion"):
            qs = qs.filter(accion=g["accion"])
        if g.get("correo"):
            qs = qs.filter(usuario__correo__icontains=g["correo"].strip())
        if g.get("entidad"):
            qs = qs.filter(entidad=g["entidad"])
        zona = timezone.get_current_timezone()
        for clave, operador, hora in (("desde", "gte", time.min), ("hasta", "lte", time.max)):
            try:
                dia = datetime.strptime(g.get(clave, ""), "%Y-%m-%d").date()
            except ValueError:
                continue
            qs = qs.filter(**{f"fecha__{operador}": timezone.make_aware(datetime.combine(dia, hora), zona)})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["acciones"] = Auditoria.objects.order_by().values_list("accion", flat=True).distinct()
        ctx["entidades"] = Auditoria.objects.order_by().values_list("entidad", flat=True).distinct()
        ctx["filtros"] = self.request.GET
        return ctx
