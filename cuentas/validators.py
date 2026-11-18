from django.core.exceptions import ValidationError

from core.passwords import errores_politica


class LetrasYNumerosValidator:
    """Exige letras y números (informe, sección 8.2). El largo mínimo lo valida MinimumLengthValidator."""

    def validate(self, password, user=None):
        errores = [e for e in errores_politica(password, largo_minimo=0)]
        if errores:
            raise ValidationError(errores, code="clave_sin_letras_o_numeros")

    def get_help_text(self):
        return "Tu contraseña debe incluir letras y números."
