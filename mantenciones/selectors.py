from datetime import timedelta

from django.utils import timezone

from core.permisos import AUDITOR, JEFATURA, codigo_perfil
from inventario.models import Equipo
from inventario.selectors import equipos_visibles
from mantenciones.models import PlanMantencion, RegistroMantencion


def registros_visibles(usuario):
    """Historial al que el usuario tiene derecho: el de los equipos que puede ver."""
    qs = RegistroMantencion.objects.select_related("equipo", "equipo__categoria", "tecnico", "plantilla")
    if codigo_perfil(usuario) in (JEFATURA, AUDITOR) and not usuario.sucursal_id:
        return qs
    return qs.filter(equipo__in=equipos_visibles(usuario).values("pk"))


def planes_pendientes(equipos, dias_adelante: int = 7):
    """Planes activos vencidos o que vencen dentro de `dias_adelante` días, ordenados por urgencia."""
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=dias_adelante)
    planes = (
        PlanMantencion.objects.filter(activo=True, equipo__in=equipos.exclude(estado=Equipo.BAJA).values("pk"))
        .select_related("equipo", "plantilla")
    )
    pendientes = [p for p in planes if p.proxima_fecha() <= limite]
    pendientes.sort(key=lambda p: p.proxima_fecha())
    return pendientes
