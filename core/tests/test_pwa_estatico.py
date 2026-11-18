"""Comprobaciones de la PWA que no necesitan Django: archivos, etiquetas y tamaños de los íconos."""
import re
import struct
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _leer(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


def _tamano_png(ruta: str) -> tuple[int, int]:
    datos = (RAIZ / ruta).read_bytes()
    assert datos[:8] == b"\x89PNG\r\n\x1a\n", f"{ruta} no es un PNG"
    return struct.unpack(">II", datos[16:24])


class PWAEstatica(unittest.TestCase):
    def test_las_dos_bases_declaran_la_app_instalable(self):
        for plantilla in ("templates/base.html", "templates/base_ingreso.html"):
            html = _leer(plantilla)
            for etiqueta in ('rel="manifest"', 'name="theme-color"', "apple-mobile-web-app-capable",
                             "mobile-web-app-capable", "apple-touch-icon"):
                self.assertIn(etiqueta, html, f"{plantilla} no incluye {etiqueta}")

    def test_iconos_del_manifiesto_con_su_tamano(self):
        self.assertEqual(_tamano_png("static/img/icon-192.png"), (192, 192))
        self.assertEqual(_tamano_png("static/img/icon-512.png"), (512, 512))
        self.assertEqual(_tamano_png("static/img/icon-maskable-512.png"), (512, 512))

    def test_service_worker_cubre_instalacion_cache_y_sin_conexion(self):
        sw = _leer("core/pwa/sw.js")
        for evento in ("install", "activate", "fetch", "message"):
            self.assertRegex(sw, rf"addEventListener\('{evento}'")
        self.assertIn("/offline/", sw)
        self.assertIn("__VERSION__", sw)

    def test_la_app_registra_el_service_worker_en_la_raiz(self):
        self.assertRegex(_leer("static/js/app.js"), r"serviceWorker\.register\('/sw\.js', \{ scope: '/' \}\)")

    def test_hay_cola_local_para_trabajar_sin_senal(self):
        self.assertIn("indexedDB", _leer("static/js/db.js"))
        self.assertRegex(_leer("static/js/sync.js"), r"encolar")

    def test_boton_de_instalar_usa_el_aviso_del_navegador(self):
        js = _leer("static/js/instalar.js")
        self.assertIn("beforeinstallprompt", js)
        self.assertIn("appinstalled", js)
        self.assertRegex(_leer("templates/cuentas/perfil.html"), r"js/instalar\.js")

    def test_el_manifiesto_se_sirve_con_modo_standalone(self):
        vista = _leer("core/views.py")
        self.assertRegex(vista, r'"display": "standalone"')
        self.assertRegex(vista, r'"purpose": "maskable"')
        self.assertIsNotNone(re.search(r'"start_url": "/"', vista))


if __name__ == "__main__":
    unittest.main()
