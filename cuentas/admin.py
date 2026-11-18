from django.contrib import admin

from cuentas.models import Perfil, TokenAcceso, Usuario


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre")


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("correo", "nombre", "apellido", "perfil", "sucursal", "is_active")
    list_filter = ("perfil", "is_active")
    search_fields = ("correo", "nombre", "apellido")
    readonly_fields = ("password", "totp_secreto", "last_login", "fecha_creacion")
    exclude = ("groups", "user_permissions")


@admin.register(TokenAcceso)
class TokenAccesoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "tipo", "creado", "expira", "usado")
    readonly_fields = ("token_hash",)
