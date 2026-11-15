"""Perfiles, permisos y decoradores de control de acceso (informe, secciones 8.1 y 8.2).

Principio de mínimo privilegio: los permisos se validan en el servidor en cada vista.
Un intento sin permiso se rechaza (403) y queda registrado en la auditoría.
"""

from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied

JEFATURA = "jefatura"
TECNICO_INTERNO = "tecnico_interno"
TECNICO_EXTERNO = "tecnico_externo"
TRABAJADOR = "trabajador"
AUDITOR = "auditor"

TECNICOS = (TECNICO_INTERNO, TECNICO_EXTERNO)
PERFILES_2FA = (JEFATURA, AUDITOR)  # verificación en dos pasos obligatoria

PERFILES = {
    JEFATURA: {
        "nombre": "Jefatura",
        "permisos": [
            "usuarios.gestionar", "equipos.gestionar", "plantillas.gestionar", "planes.gestionar",
            "tickets.crear", "tickets.aprobar", "tickets.cerrar", "historial.ver", "auditoria.ver",
        ],
    },
    TECNICO_INTERNO: {
        "nombre": "Técnico interno",
        "permisos": [
            "mantenciones.registrar", "tickets.crear", "tickets.ejecutar", "historial.ver",
            "equipos.ver_sucursal",
        ],
    },
    TECNICO_EXTERNO: {
        "nombre": "Técnico externo",
        "permisos": ["mantenciones.registrar", "tickets.ejecutar", "equipos.ver_asignados"],
    },
    TRABAJADOR: {"nombre": "Trabajador de COVEPA", "permisos": ["tickets.crear"]},
    AUDITOR: {"nombre": "Auditor", "permisos": ["auditoria.ver", "historial.ver"]},
}


def codigo_perfil(usuario) -> str | None:
    if not getattr(usuario, "is_authenticated", False):
        return None
    perfil = getattr(usuario, "perfil", None)
    return perfil.codigo if perfil else None


def redirect_to_login(*args, **kwargs):
    """Import diferido: django.contrib.auth.views carga el modelo de usuario al importarse, y este módulo
    lo importa cuentas.models antes de que ese modelo exista."""
    from django.contrib.auth.views import redirect_to_login as _redirigir

    return _redirigir(*args, **kwargs)


def _denegar(request, motivo: str):
    from auditoria.services import registrar

    registrar(
        getattr(request, "user", None),
        "acceso_denegado",
        "ruta",
        detalle={"ruta": request.path, "metodo": request.method, "motivo": motivo},
        request=request,
    )
    raise PermissionDenied(motivo)


def perfil_requerido(*codigos: str):
    """Decorador para vistas basadas en funciones."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if codigo_perfil(request.user) not in codigos:
                _denegar(request, f"Perfil sin acceso (requiere: {', '.join(codigos)}).")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


class PerfilRequeridoMixin:
    """Mixin para vistas basadas en clases. Defina `perfiles = (JEFATURA, ...)`."""

    perfiles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if codigo_perfil(request.user) not in self.perfiles:
            _denegar(request, f"Perfil sin acceso (requiere: {', '.join(self.perfiles)}).")
        return super().dispatch(request, *args, **kwargs)
