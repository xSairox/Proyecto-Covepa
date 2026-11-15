from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CorreoBackend(ModelBackend):
    """Autenticación por correo (sin distinguir mayúsculas). Rechaza cuentas inactivas o bloqueadas."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        Usuario = get_user_model()
        correo = (username or kwargs.get("correo") or "").strip().lower()
        if not correo or password is None:
            return None
        try:
            usuario = Usuario._default_manager.get(correo=correo)
        except Usuario.DoesNotExist:
            Usuario().set_password(password)  # iguala el tiempo de respuesta
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and not user.esta_bloqueado()
