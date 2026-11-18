from django.contrib import admin

from auditoria.models import Auditoria


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion", "entidad", "entidad_id", "ip")
    list_filter = ("accion", "entidad")
    search_fields = ("usuario__correo", "entidad_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
