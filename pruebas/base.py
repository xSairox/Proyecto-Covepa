"""Base común de las pruebas con base de datos: `python manage.py test pruebas`.

Cada prueba parte con MongoDB y Cloudinary reemplazados por dobles en memoria (sin red)."""

import json
import uuid
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.cloudinary_service import CloudinaryFalso, fijar_servicio
from core.mongo import RepoMemoria, fijar_repo
from core.permisos import AUDITOR, JEFATURA, TECNICO_EXTERNO, TECNICO_INTERNO, TRABAJADOR
from cuentas.models import Perfil, Usuario
from inventario.models import Categoria, Equipo, Sucursal
from mantenciones.models import Plantilla

CLAVE = "Fresia2026ok"

CAMPOS_GENERADOR = [
    {"clave": "horometro_inicial", "etiqueta": "Horómetro inicial", "tipo": "numero", "obligatorio": True, "min": 0, "unidad": "h"},
    {"clave": "horometro_final", "etiqueta": "Horómetro final", "tipo": "numero", "obligatorio": True, "mayor_que": "horometro_inicial", "unidad": "h"},
    {"clave": "nivel_aceite_ok", "etiqueta": "¿Nivel de aceite correcto?", "tipo": "si_no", "obligatorio": True},
    {"clave": "foto_equipo", "etiqueta": "Foto del equipo", "tipo": "foto", "obligatorio": True},
    {"clave": "video_arranque", "etiqueta": "Video de arranque", "tipo": "video"},
]


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fresia = Sucursal.objects.create(nombre="Fresia", comuna="Fresia", prefijo="FRE")
        cls.otra = Sucursal.objects.create(nombre="Puerto Montt", comuna="Puerto Montt", prefijo="PMO")
        cls.cat_gen = Categoria.objects.create(nombre="Generador", prefijo="GEN")
        cls.cat_ups = Categoria.objects.create(nombre="UPS", prefijo="UPS")
        cls.jefa = cls.usuario("jefa@covepa.cl", JEFATURA, cls.fresia)
        cls.auditor = cls.usuario("auditor@covepa.cl", AUDITOR, cls.fresia)
        cls.tecnico = cls.usuario("tecnico@covepa.cl", TECNICO_INTERNO, cls.fresia)
        cls.tecnico2 = cls.usuario("tecnico2@covepa.cl", TECNICO_INTERNO, cls.fresia)
        cls.externo = cls.usuario("externo@proveedor.cl", TECNICO_EXTERNO, None, empresa_externa="Servicios Sur")
        cls.trabajador = cls.usuario("trabajador@covepa.cl", TRABAJADOR, cls.fresia)
        cls.gen = Equipo.objects.create(nombre="Generador principal", categoria=cls.cat_gen, sucursal=cls.fresia)
        cls.ups = Equipo.objects.create(nombre="UPS sala servidores", categoria=cls.cat_ups, sucursal=cls.fresia)
        cls.gen_otra = Equipo.objects.create(nombre="Generador Puerto Montt", categoria=cls.cat_gen, sucursal=cls.otra)
        cls.ups.tecnicos_externos.add(cls.externo)  # el externo solo ve la UPS

    @staticmethod
    def usuario(correo, codigo, sucursal, **extra):
        perfil = Perfil.objects.get(codigo=codigo)
        nombre = correo.split("@")[0].capitalize()
        return Usuario.objects.create_user(correo, CLAVE, nombre=nombre, apellido="Prueba", perfil=perfil, sucursal=sucursal, **extra)

    def setUp(self):
        self.repo = RepoMemoria()
        self.nube = CloudinaryFalso()
        fijar_repo(self.repo)
        fijar_servicio(self.nube)
        self.addCleanup(fijar_repo, None)
        self.addCleanup(fijar_servicio, None)
        self.plantilla = Plantilla.objects.create(nombre="Generador · prueba semanal", categoria=self.cat_gen)
        self.plantilla.publicar_version(CAMPOS_GENERADOR)

    # ---------------------------------------------------------------- ayudas
    def entrar(self, usuario, cliente=None):
        cliente = cliente or self.client
        cliente.force_login(usuario)
        sesion = cliente.session
        sesion["otp_verificado"] = True
        sesion.save()
        return cliente

    def foto(self, nombre="foto1", bytes_=200_000):
        """Registra una foto en el Cloudinary falso y devuelve la evidencia que enviaría el celular."""
        url = self.nube.registrar(nombre, "foto", bytes_)
        return {"campo": "foto_equipo", "tipo": "foto", "url": url, "public_id": nombre, "peso_kb": bytes_ // 1024}

    def video(self, nombre="video1", duracion=20.0, bytes_=3_000_000):
        url = self.nube.registrar(nombre, "video", bytes_, duracion)
        return {"campo": "video_arranque", "tipo": "video", "url": url, "public_id": nombre, "peso_kb": bytes_ // 1024, "duracion_seg": duracion}

    def documento(self, usuario=None, equipo=None, **cambios):
        usuario, equipo = usuario or self.tecnico, equipo or self.gen
        ahora = timezone.now()
        doc = {
            "_id": str(uuid.uuid4()),
            "equipo": {"codigo": equipo.codigo, "categoria": equipo.categoria.nombre},
            "sucursal": equipo.sucursal.nombre,
            "plantilla": {"id": self.plantilla.pk, "nombre": self.plantilla.nombre, "version": 1},
            "tecnico_id": usuario.pk,
            "inicio": (ahora - timedelta(minutes=20)).isoformat(),
            "termino": ahora.isoformat(),
            "respuestas": {"horometro_inicial": 1200, "horometro_final": 1203.5, "nivel_aceite_ok": True},
            "evidencias": [self.foto(f"foto-{uuid.uuid4().hex[:8]}")],
            "origen": "app_movil_sin_conexion",
        }
        doc.update(cambios)
        return doc

    def sincronizar(self, doc, cliente=None):
        return (cliente or self.client).post("/api/v1/mantenciones/sincronizar/", data=json.dumps(doc), content_type="application/json")
