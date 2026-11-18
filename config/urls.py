from django.contrib import admin
from django.urls import include, path

from core import views as core_views

handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"

urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("panel/", core_views.panel, name="panel"),
    path("mas/", core_views.mas, name="mas"),
    path("offline/", core_views.offline, name="offline"),
    path("sw.js", core_views.service_worker, name="service_worker"),
    path("manifest.webmanifest", core_views.manifest, name="manifest"),
    path("salud/", core_views.salud, name="salud"),
    path("cron/vencimientos/", core_views.cron_vencimientos, name="cron_vencimientos"),
    path("cuentas/", include("cuentas.urls")),
    path("equipos/", include("inventario.urls")),
    path("mantenciones/", include("mantenciones.urls")),
    path("tickets/", include("tickets.urls")),
    path("avisos/", include("notificaciones.urls")),
    path("auditoria/", include("auditoria.urls")),
    path("api/v1/", include("mantenciones.api_urls")),
    path("gestion-interna/", admin.site.urls),  # solo superusuarios del equipo técnico
]
