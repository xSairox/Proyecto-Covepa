"""Datos de demostración del piloto Fresia: python manage.py seed_demo [--clave ...]

Es idempotente: se puede ejecutar varias veces sin duplicar nada. En producción exige --forzar."""

import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.permisos import AUDITOR, JEFATURA, PERFILES, TECNICO_EXTERNO, TECNICO_INTERNO, TRABAJADOR
from cuentas.models import Perfil, Usuario
from inventario.models import Categoria, Equipo, Sucursal
from mantenciones.models import Plantilla, PlanMantencion

CATEGORIAS = [
    ("Generador", "GEN"), ("UPS", "UPS"), ("Servidor", "SRV"), ("Switch de red", "SWT"),
    ("Cámara de seguridad", "CAM"), ("Iluminación", "ILU"), ("Aire acondicionado", "AAC"),
]

CAMPOS_GENERADOR = [
    {"clave": "horometro_inicial", "etiqueta": "Horómetro inicial", "tipo": "numero", "obligatorio": True, "min": 0, "unidad": "h"},
    {"clave": "horometro_final", "etiqueta": "Horómetro final", "tipo": "numero", "obligatorio": True, "mayor_que": "horometro_inicial", "unidad": "h"},
    {"clave": "nivel_aceite_ok", "etiqueta": "¿Nivel de aceite correcto?", "tipo": "si_no", "obligatorio": True},
    {"clave": "nivel_combustible", "etiqueta": "Nivel de combustible", "tipo": "lista", "opciones": ["Lleno", "Medio", "Bajo", "Crítico"], "obligatorio": True},
    {"clave": "temperatura", "etiqueta": "Temperatura de operación", "tipo": "numero", "min": 0, "max": 150, "unidad": "°C"},
    {"clave": "observaciones", "etiqueta": "Observaciones", "tipo": "texto"},
    {"clave": "foto_equipo", "etiqueta": "Foto del equipo", "tipo": "foto", "obligatorio": True},
    {"clave": "video_arranque", "etiqueta": "Video de arranque (máx. 30 s)", "tipo": "video"},
]

CAMPOS_UPS = [
    {"clave": "carga_bateria", "etiqueta": "Carga de la batería", "tipo": "numero", "obligatorio": True, "min": 0, "max": 100, "unidad": "%"},
    {"clave": "alarmas_activas", "etiqueta": "¿Hay alarmas activas?", "tipo": "si_no", "obligatorio": True},
    {"clave": "observaciones", "etiqueta": "Observaciones", "tipo": "texto"},
    {"clave": "foto_panel", "etiqueta": "Foto del panel", "tipo": "foto"},
]


class Command(BaseCommand):
    help = "Crea la sucursal Fresia, categorías, equipos, plantillas, un plan y un usuario por perfil."

    def add_arguments(self, parser):
        parser.add_argument("--clave", help="Contraseña de todos los usuarios de demostración (por defecto se genera una).")
        parser.add_argument("--forzar", action="store_true", help="Permite ejecutarlo con DEBUG apagado.")

    def handle(self, *args, **opciones):
        if not settings.DEBUG and not opciones["forzar"]:
            raise CommandError("seed_demo crea usuarios con una contraseña conocida. Con DEBUG apagado exige --forzar.")
        clave = opciones["clave"] or f"{secrets.token_hex(4)}Covepa{secrets.randbelow(90) + 10}"

        for codigo, datos in PERFILES.items():
            Perfil.objects.update_or_create(codigo=codigo, defaults={"nombre": datos["nombre"], "permisos": datos["permisos"]})
        fresia, _ = Sucursal.objects.get_or_create(prefijo="FRE", defaults={"nombre": "Fresia", "comuna": "Fresia"})
        categorias = {p: Categoria.objects.get_or_create(prefijo=p, defaults={"nombre": n})[0] for n, p in CATEGORIAS}

        equipos = []
        for nombre, prefijo in (("Generador principal", "GEN"), ("UPS sala de servidores", "UPS")):
            equipo = Equipo.objects.filter(nombre=nombre, sucursal=fresia).first() or Equipo.objects.create(
                nombre=nombre, categoria=categorias[prefijo], sucursal=fresia, ubicacion="Casa matriz Fresia"
            )
            equipos.append(equipo)

        plantilla_gen = self._plantilla("Generador · prueba semanal", categorias["GEN"], CAMPOS_GENERADOR)
        self._plantilla("UPS · revisión mensual", categorias["UPS"], CAMPOS_UPS)
        PlanMantencion.objects.get_or_create(
            equipo=equipos[0], plantilla=plantilla_gen, actividad="Prueba semanal de arranque", defaults={"frecuencia_dias": 7, "duracion_min": 20}
        )

        usuarios = [
            ("jefatura@covepa.test", JEFATURA, "Camila", "Jefatura", fresia, ""),
            ("tecnico@covepa.test", TECNICO_INTERNO, "Tomás", "Técnico", fresia, ""),
            ("externo@covepa.test", TECNICO_EXTERNO, "Elena", "Externa", None, "Servicios Sur Ltda."),
            ("trabajador@covepa.test", TRABAJADOR, "Bruno", "Trabajador", fresia, ""),
            ("auditor@covepa.test", AUDITOR, "Alicia", "Auditora", fresia, ""),
        ]
        for correo, codigo, nombre, apellido, sucursal, empresa in usuarios:
            usuario, creado = Usuario.objects.get_or_create(
                correo=correo,
                defaults={"nombre": nombre, "apellido": apellido, "perfil": Perfil.objects.get(codigo=codigo), "sucursal": sucursal, "empresa_externa": empresa},
            )
            if creado:
                usuario.set_password(clave)
                usuario.save()
            if codigo == TECNICO_EXTERNO:
                equipos[1].tecnicos_externos.add(usuario)  # el externo solo ve la UPS

        self.stdout.write(self.style.SUCCESS("Datos de demostración listos."))
        self.stdout.write(f"Contraseña de los usuarios nuevos: {clave}")
        for correo, codigo, *_ in usuarios:
            self.stdout.write(f"  {codigo:16} {correo}")
        self.stdout.write("Jefatura y auditor deberán activar la verificación en dos pasos al ingresar.")

    @staticmethod
    def _plantilla(nombre, categoria, campos):
        plantilla, _ = Plantilla.objects.get_or_create(nombre=nombre, categoria=categoria)
        if plantilla.version_actual == 0:
            plantilla.publicar_version(campos)
        return plantilla
