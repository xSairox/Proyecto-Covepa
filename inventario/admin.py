from django.contrib import admin

from inventario.models import Categoria, Equipo, Sucursal, VersionSoftware


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "comuna", "prefijo")


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "prefijo")


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "categoria", "sucursal", "estado")
    list_filter = ("categoria", "sucursal", "estado")
    search_fields = ("codigo", "nombre")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VersionSoftware)
class VersionSoftwareAdmin(admin.ModelAdmin):
    list_display = ("equipo", "tipo", "version", "fecha", "actual")
