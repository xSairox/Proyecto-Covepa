from django import forms
from django.contrib.auth import authenticate
from django.conf import settings

from core.forms import EstiloFormMixin
from core.permisos import TECNICO_EXTERNO, TECNICO_INTERNO, TRABAJADOR
from cuentas import services
from cuentas.models import Perfil, Usuario


class FormularioLogin(EstiloFormMixin, forms.Form):
    correo = forms.EmailField(label="Correo", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.usuario = None

    def clean(self):
        datos = super().clean()
        correo = (datos.get("correo") or "").strip().lower()
        clave = datos.get("password")
        if not correo or not clave:
            return datos
        existente = Usuario.objects.filter(correo=correo).select_related("perfil").first()
        if existente and existente.esta_bloqueado():
            raise forms.ValidationError(
                f"La cuenta está bloqueada por {settings.POLITICAS['BLOQUEO_MIN']} minutos tras demasiados intentos fallidos."
            )
        usuario = authenticate(self.request, username=correo, password=clave)
        if usuario is None:
            bloqueada = services.registrar_fallo(existente, correo, self.request)
            if bloqueada:
                raise forms.ValidationError(
                    f"Demasiados intentos fallidos: la cuenta quedó bloqueada por {settings.POLITICAS['BLOQUEO_MIN']} minutos."
                )
            raise forms.ValidationError("Correo o contraseña incorrectos.")
        self.usuario = usuario
        return datos


class FormularioCodigo(EstiloFormMixin, forms.Form):
    codigo = forms.CharField(
        label="Código de 6 dígitos",
        max_length=7,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True}),
    )


class FormularioRecuperar(EstiloFormMixin, forms.Form):
    correo = forms.EmailField(label="Correo")


class FormularioUsuario(EstiloFormMixin, forms.ModelForm):
    perfil = forms.ModelChoiceField(queryset=Perfil.objects.all(), label="Perfil", empty_label=None)

    class Meta:
        model = Usuario
        fields = ["nombre", "apellido", "correo", "perfil", "sucursal", "empresa_externa"]
        labels = {"sucursal": "Sucursal", "empresa_externa": "Empresa externa"}

    def clean_correo(self):
        return self.cleaned_data["correo"].strip().lower()

    def clean(self):
        datos = super().clean()
        perfil, sucursal = datos.get("perfil"), datos.get("sucursal")
        if perfil and perfil.codigo in (TECNICO_INTERNO, TRABAJADOR) and not sucursal:
            self.add_error("sucursal", "Este perfil debe pertenecer a una sucursal.")
        if perfil and perfil.codigo == TECNICO_EXTERNO and not datos.get("empresa_externa"):
            self.add_error("empresa_externa", "Indica la empresa externa del técnico.")
        return datos


from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm  # noqa: E402


class FormularioNuevaClave(EstiloFormMixin, SetPasswordForm):
    """Definir contraseña desde un enlace de invitación o recuperación."""


class FormularioCambiarClave(EstiloFormMixin, PasswordChangeForm):
    """Cambiar la contraseña estando con la sesión iniciada."""
