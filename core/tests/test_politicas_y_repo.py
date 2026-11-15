"""Contraseñas, repositorio MongoDB en memoria, cifrado y máquina de estados de tickets (sin Django)."""

import threading
import unittest
from decimal import Decimal

from core.mongo import RepoMemoria
from core.passwords import errores_politica
from core.validators import ErrorValidacion
from tickets import estados
from tickets.validacion import normalizar_documentos, normalizar_materiales


class PoliticaDeContrasenas(unittest.TestCase):
    def test_acepta_clave_valida(self):
        self.assertEqual(errores_politica("Fresia2026ok"), [])

    def test_rechaza_corta_sin_letras_o_sin_numeros(self):
        self.assertTrue(errores_politica("abc123"))  # corta
        self.assertTrue(any("letras" in e for e in errores_politica("1234567890")))
        self.assertTrue(any("números" in e for e in errores_politica("abcdefghijk")))


class RepoMongoEnMemoria(unittest.TestCase):
    def test_cp02_insertar_dos_veces_el_mismo_id_deja_un_solo_documento(self):
        repo = RepoMemoria()
        doc = {"_id": "u-1", "respuestas": {"a": 1}}
        self.assertTrue(repo.insertar_formulario(doc))
        self.assertFalse(repo.insertar_formulario({"_id": "u-1", "respuestas": {"a": 999}}))
        self.assertEqual(repo.ids_formularios(), {"u-1"})
        self.assertEqual(repo.obtener_formulario("u-1")["respuestas"]["a"], 1)  # no se sobrescribe

    def test_los_documentos_se_copian(self):
        repo = RepoMemoria()
        doc = {"_id": "u-2", "respuestas": {"a": 1}}
        repo.insertar_formulario(doc)
        doc["respuestas"]["a"] = 2
        self.assertEqual(repo.obtener_formulario("u-2")["respuestas"]["a"], 1)

    def test_insercion_concurrente_acepta_solo_una(self):
        repo = RepoMemoria()
        resultados = []
        hilos = [threading.Thread(target=lambda: resultados.append(repo.insertar_formulario({"_id": "x"}))) for _ in range(20)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(resultados.count(True), 1)

    def test_versiones_de_plantilla_son_correlativas_y_conservan_historial(self):
        repo = RepoMemoria()
        v1 = repo.crear_version(7, "Generador", [{"clave": "a"}])
        v2 = repo.crear_version(7, "Generador", [{"clave": "a"}, {"clave": "b"}])
        otra = repo.crear_version(8, "UPS", [])
        self.assertEqual((v1["numero"], v2["numero"], otra["numero"]), (1, 2, 1))
        self.assertEqual(len(repo.obtener_version(7, 1)["campos"]), 1)  # los registros viejos ven su versión
        self.assertEqual(repo.obtener_version(7)["numero"], 2)
        self.assertEqual([v["numero"] for v in repo.listar_versiones(7)], [2, 1])
        self.assertIsNone(repo.obtener_version(99))


class MaquinaDeEstados(unittest.TestCase):
    def test_flujo_completo(self):
        for actual, nuevo in [("Pendiente", "Aprobado"), ("Aprobado", "En ejecución"), ("En ejecución", "Realizado"), ("Realizado", "Cerrado")]:
            estados.validar_transicion(actual, nuevo)

    def test_rechazo_y_devolucion(self):
        estados.validar_transicion("Pendiente", "Rechazado")
        estados.validar_transicion("Realizado", "En ejecución")
        self.assertTrue(estados.es_devolucion("Realizado", "En ejecución"))
        self.assertFalse(estados.es_devolucion("Aprobado", "En ejecución"))

    def test_transiciones_invalidas(self):
        casos = [("Pendiente", "Cerrado"), ("Pendiente", "Realizado"), ("Aprobado", "Realizado"),
                 ("Cerrado", "Pendiente"), ("Rechazado", "Aprobado"), ("Realizado", "Aprobado"), ("Cerrado", "En ejecución")]
        for actual, nuevo in casos:
            with self.assertRaises(estados.TransicionInvalida, msg=f"{actual}->{nuevo}"):
                estados.validar_transicion(actual, nuevo)

    def test_estado_desconocido(self):
        with self.assertRaises(estados.TransicionInvalida):
            estados.validar_transicion("Inventado", "Cerrado")

    def test_estados_finales_no_tienen_salida(self):
        for f in estados.ESTADOS_FINALES:
            self.assertEqual(estados.TRANSICIONES[f], set())


class MaterialesYDocumentos(unittest.TestCase):
    def test_materiales_validos_se_normalizan(self):
        r = normalizar_materiales([{"descripcion": "Filtro de aceite", "cantidad": "2,5", "unidad": "u"}])
        self.assertEqual(r[0]["cantidad"], Decimal("2.50"))

    def test_materiales_invalidos(self):
        for malo in ([{"descripcion": "", "cantidad": 1}], [{"descripcion": "x", "cantidad": 0}],
                     [{"descripcion": "x", "cantidad": "abc"}], [{"descripcion": "x", "cantidad": -3}], "texto"):
            with self.assertRaises(ErrorValidacion):
                normalizar_materiales(malo)
        self.assertEqual(normalizar_materiales(None), [])

    def test_documento_exige_foto_https_y_prefijo(self):
        ok = {"tipo": "factura", "numero": "123", "proveedor": "Repuestos Sur", "monto": "45.900", "public_id": "a/b", "url": "https://res.cloudinary.com/demo/x.jpg"}
        self.assertEqual(normalizar_documentos([ok])[0]["monto"], 45900)
        for cambio in ({"url": ""}, {"public_id": ""}, {"url": "http://x.cl/a.jpg"}, {"tipo": "boleta"}, {"monto": "abc"}, {"monto": -1}):
            with self.assertRaises(ErrorValidacion, msg=str(cambio)):
                normalizar_documentos([{**ok, **cambio}])
        with self.assertRaises(ErrorValidacion):
            normalizar_documentos([ok], prefijo_url="https://res.cloudinary.com/otra/")

    def test_limite_de_filas(self):
        with self.assertRaises(ErrorValidacion):
            normalizar_materiales([{"descripcion": "x", "cantidad": 1}] * 31)


if __name__ == "__main__":
    unittest.main()
