from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from cuentas.models import Usuario
from inventario.models import Equipo
from mantenciones.models import Plantilla, RegistroMantencion
from pruebas.base import BaseTest


class VerificarIntegridad(BaseTest):
    def correr(self, *args):
        salida = StringIO()
        call_command("verificar_integridad", *args, stdout=salida)
        return salida.getvalue()

    def test_consistentes(self):
        self.entrar(self.tecnico)
        self.sincronizar(self.documento())
        self.assertIn("consistentes", self.correr())

    def test_detecta_huerfano_en_mongodb_y_lo_elimina_si_se_pide(self):
        self.repo.insertar_formulario({"_id": "11111111-1111-4111-8111-111111111111"})
        with self.assertRaises(CommandError):
            self.correr()
        self.assertIn("eliminado", self.correr("--eliminar-huerfanos"))
        self.assertEqual(self.repo.ids_formularios(), set())

    def test_detecta_registro_sin_detalle_en_mongodb(self):
        self.entrar(self.tecnico)
        doc = self.documento()
        self.sincronizar(doc)
        self.repo.eliminar_formulario(doc["_id"])
        with self.assertRaises(CommandError):
            self.correr()
        self.assertEqual(RegistroMantencion.objects.count(), 1)  # nunca se borra el registro


class SeedDemo(BaseTest):
    @override_settings(DEBUG=True)
    def test_es_idempotente(self):
        call_command("seed_demo", "--clave", "ClaveDemo2026", stdout=StringIO())
        usuarios, equipos, plantillas = Usuario.objects.count(), Equipo.objects.count(), Plantilla.objects.count()
        call_command("seed_demo", "--clave", "ClaveDemo2026", stdout=StringIO())
        self.assertEqual((Usuario.objects.count(), Equipo.objects.count(), Plantilla.objects.count()), (usuarios, equipos, plantillas))
        self.assertTrue(Usuario.objects.get(correo="tecnico@covepa.test").check_password("ClaveDemo2026"))

    @override_settings(DEBUG=False)
    def test_en_produccion_exige_forzar(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
