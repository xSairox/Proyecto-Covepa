from django.contrib import admin

from tickets.models import DocumentoRespaldo, HistorialEstado, Material, Ticket


class HistorialInline(admin.TabularInline):
    model = HistorialEstado
    extra = 0
    readonly_fields = ("estado", "fecha", "observacion", "usuario")
    can_delete = False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "estado", "equipo", "solicitante", "tecnico", "fecha_creacion")
    list_filter = ("estado", "tipo")
    inlines = [HistorialInline]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Material)
admin.site.register(DocumentoRespaldo)
