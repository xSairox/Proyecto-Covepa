from django.apps import AppConfig
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate

SQL_FUNCION = """
CREATE OR REPLACE FUNCTION auditoria_solo_insercion() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'La tabla de auditoria es de solo insercion';
END;
$$ LANGUAGE plpgsql
"""
SQL_BORRAR_TRIGGER = "DROP TRIGGER IF EXISTS trg_auditoria_solo_insercion ON auditoria"
SQL_CREAR_TRIGGER = """
CREATE TRIGGER trg_auditoria_solo_insercion
BEFORE UPDATE OR DELETE ON auditoria
FOR EACH ROW EXECUTE FUNCTION auditoria_solo_insercion()
"""


def instalar_trigger_solo_insercion(sender=None, using=DEFAULT_DB_ALIAS, **kwargs):
    """En PostgreSQL, la base misma rechaza UPDATE y DELETE sobre la tabla de auditoría.

    Se instala al terminar las migraciones (es idempotente), de modo que también protege
    frente a quien acceda a Neon directamente. En SQLite (desarrollo) solo rige la protección
    a nivel de aplicación.
    """
    from django.db import connections

    conexion = connections[using]
    if conexion.vendor != "postgresql":
        return
    if "auditoria" not in conexion.introspection.table_names():
        return
    with conexion.cursor() as cursor:
        cursor.execute(SQL_FUNCION)
        cursor.execute(SQL_BORRAR_TRIGGER)
        cursor.execute(SQL_CREAR_TRIGGER)


class AuditoriaConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "auditoria"
    verbose_name = "Auditoría"

    def ready(self):
        post_migrate.connect(instalar_trigger_solo_insercion, sender=self)
