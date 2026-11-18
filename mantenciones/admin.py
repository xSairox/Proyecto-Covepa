from django.contrib import admin

from mantenciones.models import PlanMantencion, Plantilla, RegistroMantencion


@admin.register(Plantilla)
class PlantillaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "version_actual", "activa")


@admin.register(PlanMantencion)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("actividad", "equipo", "frecuencia_dias", "ultima_fecha", "activo")


@admin.register(RegistroMantencion)
class RegistroAdmin(admin.ModelAdmin):
    list_display = ("equipo", "tecnico", "inicio", "estado_sync")
    readonly_fields = ("id", "equipo", "tecnico", "plantilla", "version_plantilla", "plan", "inicio", "termino", "origen")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
