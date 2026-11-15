"""Middleware de sesión por perfil, verificación en dos pasos y cabeceras de seguridad."""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from core.permisos import PERFILES_2FA, TECNICOS, codigo_perfil

# Rutas accesibles sin haber completado el segundo paso
_RUTAS_LIBRES_2FA = ("/cuentas/2fa/", "/cuentas/logout/", "/static/", "/sw.js", "/manifest.webmanifest", "/salud/", "/cron/")

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://res.cloudinary.com; "
    "media-src 'self' blob: https://res.cloudinary.com; "
    "connect-src 'self' https://api.cloudinary.com; "
    "worker-src 'self'; manifest-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class PerfilSesionMiddleware:
    """Aplica la duración de sesión según el perfil y exige el segundo paso a jefatura y auditor.

    - Técnicos: la sesión dura la jornada (12 h) porque trabajan en terreno y sin señal.
    - Resto de perfiles: cierre automático tras 30 minutos de inactividad.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user
        if usuario.is_authenticated:
            codigo = codigo_perfil(usuario)
            politicas = settings.POLITICAS
            if codigo in TECNICOS:
                request.session.set_expiry(politicas["SESION_TECNICO_HORAS"] * 3600)
            else:
                request.session.set_expiry(politicas["SESION_STAFF_MIN"] * 60)

            if (
                codigo in PERFILES_2FA
                and not request.session.get("otp_verificado")
                and not request.path.startswith(_RUTAS_LIBRES_2FA)
            ):
                return redirect(reverse("cuentas:dos_pasos"))
        return self.get_response(request)


class CabecerasSeguridadMiddleware:
    """Content-Security-Policy estricta: no se permite JavaScript en línea."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if not request.path.startswith("/gestion-interna/"):  # el admin de Django usa scripts en línea
            respuesta.headers.setdefault("Content-Security-Policy", CSP)
        respuesta.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        return respuesta
