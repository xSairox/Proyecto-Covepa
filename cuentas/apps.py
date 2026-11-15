from django.apps import AppConfig
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate


def crear_perfiles(sender=None, using=DEFAULT_DB_ALIAS, apps=None, **kwargs):
    """Deja los cinco perfiles del informe (sección 8.1) siempre disponibles tras migrar."""
    from core.permisos import PERFILES

    Perfil = (apps or sender.apps).get_model("cuentas", "Perfil")
    for codigo, datos in PERFILES.items():
        Perfil.objects.using(using).update_or_create(
            codigo=codigo, defaults={"nombre": datos["nombre"], "permisos": datos["permisos"]}
        )


class CuentasConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "cuentas"
    verbose_name = "Cuentas y perfiles"

    def ready(self):
        post_migrate.connect(crear_perfiles, sender=self)
