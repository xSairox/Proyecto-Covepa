import hmac
import logging
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.mongo import obtener_repo
from core.permisos import (
    AUDITOR,
    JEFATURA,
    TECNICO_EXTERNO,
    TECNICO_INTERNO,
    TRABAJADOR,
    codigo_perfil,
    perfil_requerido,
)

logger = logging.getLogger("covepa")

VERSION_APP = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "desarrollo")[:12]


@login_required
def inicio(request):
    """Lleva a cada perfil a su pantalla de inicio (informe, sección 6.3)."""
    destinos = {
        JEFATURA: "panel",
        TECNICO_INTERNO: "mantenciones:inicio",
        TECNICO_EXTERNO: "mantenciones:inicio",
        TRABAJADOR: "tickets:lista",
        AUDITOR: "auditoria:lista",
    }
    return redirect(destinos.get(codigo_perfil(request.user), "cuentas:perfil"))


@perfil_requerido(JEFATURA)
def panel(request):
    """Indicadores y pendientes de la jefatura."""
    from inventario.models import Equipo
    from inventario.selectors import equipos_visibles
    from mantenciones.models import RegistroMantencion
    from mantenciones.selectors import planes_pendientes, registros_visibles
    from tickets import estados
    from tickets.services import tickets_visibles

    equipos = equipos_visibles(request.user)
    tickets = tickets_visibles(request.user)
    hoy = timezone.localdate()
    pendientes = planes_pendientes(equipos, dias_adelante=7)
    vencidos = [p for p in pendientes if p.proxima_fecha() < hoy]
    contexto = {
        "total_equipos": equipos.exclude(estado=Equipo.BAJA).count(),
        "en_mantencion": equipos.filter(estado=Equipo.EN_MANTENCION).count(),
        "vencidos": vencidos[:8],
        "total_vencidos": len(vencidos),
        "proximos": [p for p in pendientes if p.proxima_fecha() >= hoy][:8],
        "por_aprobar": tickets.filter(estado=estados.PENDIENTE).select_related("equipo")[:8],
        "total_por_aprobar": tickets.filter(estado=estados.PENDIENTE).count(),
        "por_cerrar": tickets.filter(estado=estados.REALIZADO).select_related("equipo")[:8],
        "total_por_cerrar": tickets.filter(estado=estados.REALIZADO).count(),
        "mantenciones_30d": registros_visibles(request.user).filter(inicio__gte=timezone.now() - timedelta(days=30)).count(),
        "hoy": hoy,
    }
    return render(request, "core/panel.html", contexto)


@perfil_requerido(JEFATURA)
def mas(request):
    return render(request, "core/mas.html")


def offline(request):
    return render(request, "core/offline.html")


# --------------------------------------------------------------------------- PWA


@never_cache
@require_GET
def service_worker(request):
    """Se sirve desde la raíz para que controle todo el sitio. La versión invalida cachés en cada despliegue."""
    codigo = (Path(__file__).parent / "pwa" / "sw.js").read_text(encoding="utf-8").replace("__VERSION__", VERSION_APP)
    respuesta = HttpResponse(codigo, content_type="application/javascript; charset=utf-8")
    respuesta["Service-Worker-Allowed"] = "/"
    return respuesta


@require_GET
def manifest(request):
    datos = {
        "name": "COVEPA Mantenciones",
        "short_name": "Mantenciones",
        "description": "Inventario y mantención de equipos de COVEPA. Funciona sin conexión.",
        "lang": "es-CL",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#F5F5F2",
        "theme_color": "#FFFFFF",
        "icons": [
            {"src": static("img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("img/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("img/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JsonResponse(datos, content_type="application/manifest+json")


# --------------------------------------------------------------------------- monitoreo y tareas programadas


@never_cache
def salud(request):
    """Comprobación de estado para monitoreo. No expone datos sensibles."""
    estado = {"postgres": False, "mongodb": False, "cloudinary": settings.CLOUDINARY_ENABLED, "version": VERSION_APP}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        estado["postgres"] = True
    except Exception:  # noqa: BLE001
        logger.exception("Falla de PostgreSQL en /salud/")
    try:
        estado["mongodb"] = bool(obtener_repo().ping())
    except Exception:  # noqa: BLE001
        logger.exception("Falla de MongoDB en /salud/")
    sano = estado["postgres"] and estado["mongodb"]
    estado["estado"] = "ok" if sano else "degradado"
    return JsonResponse(estado, status=200 if sano else 503)


@never_cache
def cron_vencimientos(request):
    """Vercel Cron llama aquí cada día con 'Authorization: Bearer <CRON_SECRET>'."""
    secreto = settings.CRON_SECRET
    recibido = request.headers.get("Authorization", "")
    if not secreto or not hmac.compare_digest(recibido, f"Bearer {secreto}"):
        return JsonResponse({"error": "no autorizado"}, status=401)
    from notificaciones.services import generar_vencimientos

    creadas = generar_vencimientos()
    logger.info("Vencimientos: %s avisos creados", creadas)
    return JsonResponse({"avisos_creados": creadas})


# --------------------------------------------------------------------------- errores


def csrf_fallo(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse({"errores": ["Sesión o token de seguridad vencido. Recarga la aplicación."]}, status=403)
    return render(request, "403.html", {"mensaje": "Tu sesión o el token de seguridad venció. Vuelve atrás, recarga la página e inténtalo otra vez."}, status=403)


def error_403(request, exception=None):
    return render(request, "403.html", {}, status=403)


def error_404(request, exception=None):
    return render(request, "404.html", {}, status=404)


def error_500(request):
    return HttpResponse(
        "<!doctype html><meta charset=utf-8><title>Error</title><body style='font-family:sans-serif;padding:2rem'>"
        "<h1>Algo salió mal</h1><p>Ya registramos el problema. Inténtalo de nuevo en unos minutos.</p></body>",
        status=500,
    )
