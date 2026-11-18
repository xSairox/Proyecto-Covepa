"""Alcance de datos por perfil (control de acceso, OWASP A01).

Todas las vistas y APIs deben obtener los equipos a través de `equipos_visibles`,
nunca con `Equipo.objects` directamente.
"""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from auditoria import services as auditoria
from core.permisos import AUDITOR, JEFATURA, TECNICO_EXTERNO, TECNICO_INTERNO, TRABAJADOR, codigo_perfil
from inventario.models import Equipo


def equipos_visibles(usuario):
    base = Equipo.objects.select_related("categoria", "sucursal")
    codigo = codigo_perfil(usuario)
    if codigo in (JEFATURA, AUDITOR):
        return base.filter(sucursal_id=usuario.sucursal_id) if usuario.sucursal_id else base
    if codigo in (TECNICO_INTERNO, TRABAJADOR):
        return base.filter(sucursal_id=usuario.sucursal_id) if usuario.sucursal_id else base.none()
    if codigo == TECNICO_EXTERNO:
        return base.filter(tecnicos_externos=usuario)
    return base.none()


def equipo_o_403(request, pk):
    """Devuelve el equipo si el usuario puede verlo. Si existe pero no le corresponde: 403 y auditoría."""
    equipo = get_object_or_404(Equipo.objects.select_related("categoria", "sucursal"), pk=pk)
    if not equipos_visibles(request.user).filter(pk=pk).exists():
        auditoria.registrar(
            request.user,
            auditoria.ACCESO_DENEGADO,
            "equipo",
            pk,
            {"codigo": equipo.codigo, "ruta": request.path},
            request,
        )
        raise PermissionDenied("No tienes acceso a este equipo.")
    return equipo
