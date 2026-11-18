"""Explica por qué "Registrar mantención" puede salir vacío.

Uso: python manage.py diagnostico_registro correo@covepa.test

Revisa lo mismo que arma el paquete de datos del técnico: su perfil y sucursal, los equipos que puede ver
y, para cada categoría, si hay un formulario publicado en PostgreSQL con su versión guardada en MongoDB."""

from django.core.management.base import BaseCommand, CommandError

from core.permisos import TECNICO_EXTERNO, TECNICO_INTERNO, codigo_perfil
from cuentas.models import Usuario
from inventario.models import Equipo
from inventario.selectors import equipos_visibles
from mantenciones.models import Plantilla


class Command(BaseCommand):
    help = "Diagnostica por qué un técnico no ve equipos o formularios en Registrar mantención."

    def add_arguments(self, parser):
        parser.add_argument("correo", help="Correo del técnico.")

    def handle(self, *args, **opciones):
        correo = opciones["correo"].strip().lower()
        try:
            usuario = Usuario.objects.get(correo=correo)
        except Usuario.DoesNotExist:
            raise CommandError(f"No existe un usuario con el correo {correo}.") from None

        problemas = []
        perfil = codigo_perfil(usuario)
        sucursal = usuario.sucursal or "ninguna"
        self.stdout.write(f"Usuario: {usuario.correo} · perfil: {perfil} · sucursal: {sucursal}")
        if not usuario.is_active:
            problemas.append("El usuario está desactivado.")
        if perfil not in (TECNICO_INTERNO, TECNICO_EXTERNO):
            problemas.append("Solo los técnicos (interno o externo) pueden usar Registrar mantención.")
        if perfil == TECNICO_INTERNO and not usuario.sucursal_id:
            problemas.append("Es técnico interno y no tiene sucursal: no ve ningún equipo. Asígnale una.")

        equipos = list(equipos_visibles(usuario).exclude(estado=Equipo.BAJA))
        self.stdout.write(f"Equipos que puede ver (sin los dados de baja): {len(equipos)}")
        if not equipos and perfil == TECNICO_EXTERNO:
            problemas.append("Es técnico externo y no tiene equipos asignados. Asígnaselos desde el equipo.")
        elif not equipos and usuario.sucursal_id:
            problemas.append("Su sucursal no tiene equipos activos.")

        for equipo in equipos:
            plantillas = Plantilla.objects.filter(categoria_id=equipo.categoria_id, activa=True)
            disponibles = 0
            detalle = []
            for plantilla in plantillas:
                if not plantilla.version_actual:
                    detalle.append(f"«{plantilla.nombre}»: sin versión publicada")
                    continue
                try:
                    existe = plantilla.version() is not None
                except Exception as exc:  # noqa: BLE001 - se informa el motivo (p. ej. MongoDB sin conexión)
                    problemas.append(f"MongoDB no responde ({type(exc).__name__}). Revisa MONGODB_URI.")
                    existe = False
                if existe:
                    disponibles += 1
                else:
                    detalle.append(f"«{plantilla.nombre}»: publicada, pero sin su versión en MongoDB")
            categoria = equipo.categoria.nombre
            self.stdout.write(f"  {equipo.codigo} · {categoria}: {disponibles} formulario(s) disponible(s)")
            for linea in detalle:
                self.stdout.write(f"      {linea}")
            if not plantillas.exists():
                problemas.append(f"No hay plantilla activa para la categoría «{categoria}».")
            elif not disponibles:
                problemas.append(f"La categoría «{categoria}» no tiene ningún formulario disponible.")

        if problemas:
            self.stdout.write(self.style.ERROR("\nProblemas encontrados:"))
            for texto in dict.fromkeys(problemas):
                self.stdout.write(f"  - {texto}")
            self.stdout.write("\nLas plantillas se publican en Más → Plantillas de formulario (jefatura).")
            self.stdout.write("En la demostración, `manage.py seed_demo --forzar` repara las plantillas.")
        else:
            self.stdout.write(self.style.SUCCESS("\nTodo en orden: debería ver sus equipos y formularios."))
