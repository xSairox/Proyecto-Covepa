"""Plantillas versionadas (HU-03), equipos (HU-02) y piezas de la PWA (HU-05)."""

import json

from django.test import Client
from django.urls import reverse

from mantenciones.models import RegistroMantencion
from pruebas.base import CAMPOS_GENERADOR, BaseTest


class PlantillasVersionadas(BaseTest):
    def publicar_por_web(self, plantilla, campos):
        return self.client.post(
            reverse("mantenciones:plantilla_editar", args=[plantilla.pk]),
            {"nombre": plantilla.nombre, "categoria": plantilla.categoria_id, "activa": "on", "campos_json": json.dumps(campos)},
        )

    def test_cambiar_campos_crea_version_nueva_y_conserva_la_anterior(self):
        self.entrar(self.jefa)
        nuevos = CAMPOS_GENERADOR + [{"clave": "temperatura", "etiqueta": "Temperatura", "tipo": "numero", "unidad": "°C"}]
        self.assertEqual(self.publicar_por_web(self.plantilla, nuevos).status_code, 302)
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.version_actual, 2)
        self.assertEqual(len(self.repo.obtener_version(self.plantilla.pk, 1)["campos"]), len(CAMPOS_GENERADOR))
        self.assertEqual(len(self.repo.obtener_version(self.plantilla.pk, 2)["campos"]), len(CAMPOS_GENERADOR) + 1)

    def test_guardar_sin_cambiar_los_campos_no_crea_version(self):
        self.entrar(self.jefa)
        self.publicar_por_web(self.plantilla, CAMPOS_GENERADOR)
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.version_actual, 1)

    def test_un_registro_antiguo_sigue_validandose_con_su_version(self):
        antiguo = self.documento()  # el celular lo llenó con la versión 1, sin conexión
        self.publicar_por_web_con(self.jefa, [{"clave": "solo_nuevo", "etiqueta": "Nuevo", "tipo": "texto", "obligatorio": True}])
        self.entrar(self.tecnico)
        self.assertEqual(self.sincronizar(antiguo).status_code, 201)  # la versión 1 sigue existiendo
        self.assertEqual(RegistroMantencion.objects.get().version_plantilla, 1)

    def publicar_por_web_con(self, usuario, campos):
        cliente = Client()
        self.entrar(usuario, cliente)
        cliente.post(
            reverse("mantenciones:plantilla_editar", args=[self.plantilla.pk]),
            {"nombre": self.plantilla.nombre, "categoria": self.plantilla.categoria_id, "activa": "on", "campos_json": json.dumps(campos)},
        )

    def test_campos_invalidos_no_publican_nada(self):
        self.entrar(self.jefa)
        r = self.publicar_por_web(self.plantilla, [{"clave": "Mal Nombre", "etiqueta": "x", "tipo": "numero"}])
        self.assertEqual(r.status_code, 200)
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.version_actual, 1)

    def test_solo_la_jefatura_edita_plantillas(self):
        for usuario in (self.tecnico, self.auditor, self.externo, self.trabajador):
            self.entrar(usuario)
            self.assertEqual(self.client.get(reverse("mantenciones:plantilla_nueva")).status_code, 403, usuario.correo)


class Equipos(BaseTest):
    def test_codigo_se_genera_correlativo_por_tipo_y_sucursal(self):
        self.assertEqual(self.gen.codigo, "GEN-FRE-01")
        otro = self.gen.__class__.objects.create(nombre="Generador 2", categoria=self.cat_gen, sucursal=self.fresia)
        self.assertEqual(otro.codigo, "GEN-FRE-02")
        self.assertEqual(self.gen_otra.codigo, "GEN-PMO-01")
        self.assertEqual(self.ups.codigo, "UPS-FRE-01")

    def test_un_equipo_no_se_elimina_se_da_de_baja_y_conserva_su_historial(self):
        with self.assertRaises(PermissionError):
            self.gen.delete()
        self.entrar(self.tecnico)
        self.sincronizar(self.documento())
        self.gen.dar_de_baja()
        self.gen.refresh_from_db()
        self.assertEqual(self.gen.estado, "Baja")
        self.assertEqual(RegistroMantencion.objects.filter(equipo=self.gen).count(), 1)

    def test_no_se_registran_mantenciones_de_un_equipo_dado_de_baja(self):
        self.entrar(self.tecnico)
        self.gen.dar_de_baja()
        self.assertEqual(self.sincronizar(self.documento()).status_code, 400)

    def test_la_jefatura_ve_solo_su_sucursal(self):
        self.entrar(self.jefa)
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, self.gen.codigo)
        self.assertNotContains(r, self.gen_otra.codigo)

    def test_el_trabajador_no_crea_equipos(self):
        self.entrar(self.trabajador)
        self.assertEqual(self.client.get(reverse("inventario:nuevo")).status_code, 403)


class PWA(BaseTest):
    def test_service_worker_se_sirve_desde_la_raiz_con_su_version(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        cuerpo = r.content.decode()
        self.assertNotIn("__VERSION__", cuerpo)
        self.assertIn("covepa-paginas-", cuerpo)

    def test_manifest_instalable(self):
        datos = self.client.get("/manifest.webmanifest").json()
        self.assertEqual(datos["display"], "standalone")
        self.assertEqual(datos["theme_color"], "#FFFFFF")
        self.assertTrue(any(i.get("purpose") == "maskable" for i in datos["icons"]))
        self.assertTrue(any(i["sizes"] == "512x512" for i in datos["icons"]))

    def test_pagina_sin_conexion_es_publica(self):
        self.assertEqual(self.client.get("/offline/").status_code, 200)

    def test_salud_con_las_dos_bases_operativas(self):
        r = self.client.get("/salud/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["estado"], "ok")

    def test_sesion_entrega_token_csrf_para_la_app(self):
        self.entrar(self.tecnico)
        datos = self.client.get("/api/v1/sesion/").json()
        self.assertTrue(datos["autenticado"])
        self.assertTrue(datos["csrf"])
        self.assertEqual(datos["usuario"]["perfil"], "tecnico_interno")

    def test_paquete_trae_lo_necesario_para_trabajar_sin_conexion(self):
        self.entrar(self.tecnico)
        datos = self.client.get("/api/v1/paquete/").json()
        self.assertEqual({e["codigo"] for e in datos["equipos"]}, {self.gen.codigo, self.ups.codigo})
        plantilla = datos["plantillas"][str(self.plantilla.pk)]
        self.assertEqual(plantilla["version"], 1)
        self.assertEqual(len(plantilla["campos"]), len(CAMPOS_GENERADOR))
        self.assertEqual(datos["limites"]["video_max_seg"], 30)
        self.assertEqual(self.client.get("/api/v1/paquete/")["Cache-Control"], "no-store")

    def test_firma_de_cloudinary_solo_para_tipos_permitidos(self):
        self.entrar(self.tecnico)
        self.assertEqual(self.client.get("/api/v1/cloudinary/firma/?tipo=foto").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/cloudinary/firma/?tipo=video").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/cloudinary/firma/?tipo=exe").status_code, 400)

    def test_errores_personalizados(self):
        self.entrar(self.tecnico)
        self.assertEqual(self.client.get("/no-existe/").status_code, 404)
