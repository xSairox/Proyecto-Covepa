from django.contrib import admin

from notificaciones.models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("usuario", "texto", "fecha", "leida")
    list_filter = ("leida",)
