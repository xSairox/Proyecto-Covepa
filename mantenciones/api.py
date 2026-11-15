"""API JSON que usa la aplicación móvil (PWA).

Autenticación por la sesión de Django + token CSRF (cabecera X-CSRFToken). No hay API pública.
"""

from __future__ import annotations

import json
import logging
from functools import wraps

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from auditoria import services as auditoria
from core.cloudinary_service import ActivoInvalido, obtener_servicio
from core.permisos import TECNICO_EXTERNO, TECNICO_INTERNO, codigo_perfil
from mantenciones import services

logger = logging.getLogger("covepa.api")
TECNICOS = (TECNICO_INTERNO, TECNICO_EXTERNO)
MAX_BYTES_JSON = 256 * 1024


def _error(estado: int, *errores: str) -> JsonResponse:
    return JsonResponse({"errores": list(errores)}, status=estado)


def api_perfil(*codigos: str):
    """Como perfil_requerido, pero responde JSON (401/403) en vez de redirigir al login."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return _error(401, "Sesión vencida: vuelve a iniciar sesión.")
            if codigo_perfil(request.user) not in codigos:
                auditoria.registrar(
                    request.user, auditoria.ACCESO_DENEGADO, "api", detalle={"ruta": request.path, "metodo": request.method}, request=request
                )
                return _error(403, "Tu perfil no tiene acceso a este recurso.")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador


@require_GET
@ensure_csrf_cookie
def sesion(request):
    """Estado de la sesión y token CSRF vigente. La app lo consulta antes de sincronizar."""
    usuario = request.user
    return JsonResponse(
        {
            "autenticado": usuario.is_authenticated,
            "csrf": get_token(request),
            "usuario": {"id": usuario.pk, "nombre": str(usuario), "perfil": codigo_perfil(usuario)} if usuario.is_authenticated else None,
        }
    )


@require_GET
@api_perfil(*TECNICOS)
def paquete(request):
    """Paquete de datos para trabajar sin conexión (equipos, plantillas, pendientes)."""
    respuesta = JsonResponse(services.construir_paquete(request.user))
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@require_GET
@api_perfil(*TECNICOS)
def firma_cloudinary(request):
    """Parámetros firmados para subir una foto o un video directo a Cloudinary."""
    tipo = request.GET.get("tipo", "foto")
    try:
        datos = obtener_servicio().firmar_subida(tipo)
    except ActivoInvalido as exc:
        return _error(400, str(exc))
    respuesta = JsonResponse(datos)
    respuesta["Cache-Control"] = "no-store"
    return respuesta


@require_POST
@api_perfil(*TECNICOS)
def sincronizar(request):
    """Recibe un formulario de mantención (JSON). Idempotente: reenviar el mismo UUID no duplica."""
    if len(request.body) > MAX_BYTES_JSON:
        return _error(413, "El documento es demasiado grande.")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _error(400, "El cuerpo no es un JSON válido.")

    try:
        resultado = services.sincronizar_formulario(payload, request.user, request)
    except services.SincronizacionError as exc:
        return JsonResponse({"errores": exc.errores}, status=exc.http)
    except Exception:  # noqa: BLE001
        logger.exception("Error inesperado al sincronizar")
        return _error(500, "No pudimos guardar el formulario. Inténtalo de nuevo más tarde; tus datos siguen en el dispositivo.")

    return JsonResponse(
        {"estado": "creado" if resultado.creado else "duplicado", "id": str(resultado.registro.pk)},
        status=201 if resultado.creado else 200,
    )
