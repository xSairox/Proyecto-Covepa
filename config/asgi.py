import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _exigir_variables() -> None:
    """Se niega a arrancar el servidor en producción si faltan variables obligatorias."""
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    if settings.FALTAN_VARIABLES:
        raise ImproperlyConfigured(
            "Faltan variables de entorno obligatorias: " + ", ".join(settings.FALTAN_VARIABLES)
            + ". Defínelas en Vercel (Settings > Environment Variables) o en tu archivo .env."
        )


_exigir_variables()

application = get_asgi_application()
