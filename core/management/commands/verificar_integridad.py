"""Compara PostgreSQL y MongoDB: python manage.py verificar_integridad [--eliminar-huerfanos]

Como no existe una transacción entre las dos bases, una falla en el peor momento podría dejar un formulario
en una y no en la otra. Este comando lo detecta (informe, sección 7.3)."""

import uuid

from django.core.management.base import BaseCommand, CommandError

from core.mongo import obtener_repo
from mantenciones.models import RegistroMantencion


class Command(BaseCommand):
    help = "Busca registros presentes en una base y ausentes en la otra."

    def add_arguments(self, parser):
        parser.add_argument("--eliminar-huerfanos", action="store_true", help="Borra de MongoDB los formularios sin registro en PostgreSQL.")

    def handle(self, *args, **opciones):
        repo = obtener_repo()
        en_postgres = {str(pk) for pk in RegistroMantencion.objects.values_list("pk", flat=True)}
        en_mongo = {str(uuid.UUID(i)) if _es_uuid(i) else i for i in repo.ids_formularios()}

        sin_mongo = sorted(en_postgres - en_mongo)
        sin_postgres = sorted(en_mongo - en_postgres)
        self.stdout.write(f"PostgreSQL: {len(en_postgres)} registros · MongoDB: {len(en_mongo)} formularios")

        for i in sin_mongo:
            self.stdout.write(self.style.ERROR(f"Falta en MongoDB (se perdió el detalle): {i}"))
        for i in sin_postgres:
            self.stdout.write(self.style.WARNING(f"Huérfano en MongoDB (sin registro en PostgreSQL): {i}"))
            if opciones["eliminar_huerfanos"]:
                repo.eliminar_formulario(i)
                self.stdout.write(f"  eliminado {i}")

        if sin_mongo or (sin_postgres and not opciones["eliminar_huerfanos"]):
            raise CommandError(f"Inconsistencias: {len(sin_mongo)} sin detalle, {len(sin_postgres)} huérfanos.")
        self.stdout.write(self.style.SUCCESS("Las dos bases son consistentes."))


def _es_uuid(valor) -> bool:
    try:
        uuid.UUID(str(valor))
        return True
    except ValueError:
        return False
