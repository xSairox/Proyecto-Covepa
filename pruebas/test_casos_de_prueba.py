"""Casos de prueba del informe (sección 9.2): CP01 a CP09 automatizados.

CP03 (carga) está en tests/locustfile.py; CP04 y CP05 (dispositivos reales y modo sin conexión)
son manuales y están en docs/PROTOCOLO_DE_PRUEBAS.md."""

import json
from unittest import mock

from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

from auditoria import services as aud
from auditoria.models import Auditoria
from cuentas.models import Usuario
from mantenciones.models import RegistroMantencion
from pruebas.base import CLAVE, BaseTest


class CP01_CorreoDuplicado(BaseTest):
    """No se pueden crear dos usuarios con el mismo correo (aunque cambien las mayúsculas)."""

    def datos(self, correo):
        return {"nombre": "Ana", "apellido": "Soto", "correo": correo, "perfil": self.tecnico.perfil_id, "sucursal": self.fresia.pk, "empresa_externa": ""}

    def test_segundo_usuario_con_el_mismo_correo_se_rechaza(self):
        self.entrar(self.jefa)
        r1 = self.client.post(reverse("cuentas:usuario_nuevo"), self.datos("ana@covepa.cl"))
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.post(reverse("cuentas:usuario_nuevo"), self.datos("ANA@covepa.cl"))
        self.assertEqual(r2.status_code, 200)  # vuelve al formulario con el error
        self.assertEqual(Usuario.objects.filter(correo="ana@covepa.cl").count(), 1)
        self.assertTrue(r2.context["form"].errors.get("correo"))

    def test_invitacion_registra_auditoria(self):
        self.entrar(self.jefa)
        self.client.post(reverse("cuentas:usuario_nuevo"), self.datos("nueva@covepa.cl"))
        self.assertTrue(Auditoria.objects.filter(accion=aud.USUARIO_CREADO, usuario=self.jefa).exists())


class CP02_SincronizacionIdempotente(BaseTest):
    """Reenviar el mismo formulario (mala señal) no duplica datos en ninguna de las dos bases."""

    def test_enviar_dos_veces_deja_un_solo_registro_en_postgresql_y_en_mongodb(self):
        self.entrar(self.tecnico)
        doc = self.documento()
        primero = self.sincronizar(doc)
        segundo = self.sincronizar(doc)
        self.assertEqual(primero.status_code, 201)
        self.assertEqual(segundo.status_code, 200)
        self.assertEqual(segundo.json()["estado"], "duplicado")
        self.assertEqual(RegistroMantencion.objects.count(), 1)
        self.assertEqual(self.repo.ids_formularios(), {doc["_id"]})

    def test_los_datos_completos_quedan_en_mongodb_y_los_de_filtro_en_postgresql(self):
        self.entrar(self.tecnico)
        doc = self.documento()
        self.sincronizar(doc)
        guardado = self.repo.obtener_formulario(doc["_id"])
        self.assertEqual(guardado["respuestas"]["horometro_final"], 1203.5)
        self.assertEqual(guardado["equipo"]["codigo"], self.gen.codigo)
        self.assertEqual(guardado["evidencias"][0]["public_id"], doc["evidencias"][0]["public_id"])
        registro = RegistroMantencion.objects.get()
        self.assertEqual((registro.equipo, registro.tecnico, registro.version_plantilla), (self.gen, self.tecnico, 1))
        self.assertEqual(str(registro.pk), doc["_id"])

    def test_otro_tecnico_no_puede_apropiarse_de_un_uuid_ya_usado(self):
        self.entrar(self.tecnico)
        doc = self.documento()
        self.sincronizar(doc)
        otro = self.entrar(self.tecnico2, Client())
        ajeno = {**doc, "tecnico_id": self.tecnico2.pk}
        r = self.sincronizar(ajeno, otro)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(RegistroMantencion.objects.count(), 1)

    def test_si_postgresql_falla_no_queda_un_documento_huerfano_en_mongodb(self):
        self.entrar(self.tecnico)
        doc = self.documento()
        with mock.patch.object(RegistroMantencion.objects, "create", side_effect=RuntimeError("PostgreSQL caído")):
            r = self.sincronizar(doc)
        self.assertEqual(r.status_code, 500)
        self.assertEqual(self.repo.ids_formularios(), set())
        # El celular reintenta y esta vez funciona
        self.assertEqual(self.sincronizar(doc).status_code, 201)
        self.assertEqual(self.repo.ids_formularios(), {doc["_id"]})

    def test_actualiza_la_ultima_fecha_del_plan(self):
        from mantenciones.models import PlanMantencion

        plan = PlanMantencion.objects.create(equipo=self.gen, plantilla=self.plantilla, actividad="Prueba semanal", frecuencia_dias=7)
        self.entrar(self.tecnico)
        r = self.sincronizar(self.documento(plan_id=plan.pk))
        self.assertEqual(r.status_code, 201)
        plan.refresh_from_db()
        self.assertIsNotNone(plan.ultima_fecha)

    def test_exige_token_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        self.entrar(self.tecnico, cliente)
        r = self.sincronizar(self.documento(), cliente)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(RegistroMantencion.objects.count(), 0)

    def test_sin_sesion_responde_401(self):
        r = self.sincronizar(self.documento())
        self.assertEqual(r.status_code, 401)


class CP06_BloqueoPorIntentos(BaseTest):
    """Cinco intentos fallidos bloquean la cuenta 15 minutos, aunque después se use la clave correcta."""

    def intentar(self, clave):
        return self.client.post(reverse("cuentas:login"), {"correo": self.tecnico.correo, "password": clave})

    def test_quinto_intento_bloquea_y_la_clave_correcta_ya_no_sirve(self):
        for _ in range(4):
            r = self.intentar("incorrecta1")
            self.assertContains(r, "incorrectos")
        r = self.intentar("incorrecta1")
        self.assertContains(r, "bloqueada")
        r = self.intentar(CLAVE)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "bloqueada")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(Auditoria.objects.filter(accion=aud.CUENTA_BLOQUEADA, usuario=self.tecnico).exists())

    def test_login_correcto_reinicia_el_contador(self):
        for _ in range(3):
            self.intentar("incorrecta1")
        r = self.intentar(CLAVE)
        self.assertEqual(r.status_code, 302)
        self.tecnico.refresh_from_db()
        self.assertEqual(self.tecnico.intentos_fallidos, 0)

    def test_el_mensaje_no_revela_si_el_correo_existe(self):
        r = self.client.post(reverse("cuentas:login"), {"correo": "nadie@covepa.cl", "password": "cualquiera1"})
        self.assertContains(r, "Correo o contraseña incorrectos.")

    def test_cuenta_desactivada_no_ingresa_y_pierde_sus_sesiones(self):
        self.entrar(self.tecnico)
        self.assertTrue(Session.objects.exists())
        self.tecnico.desactivar()
        self.assertEqual(self.client.get("/mantenciones/inicio/").status_code, 302)  # sesión cerrada
        self.assertEqual(self.intentar(CLAVE).status_code, 200)


class CP07_HorometroFinalMayorQueInicial(BaseTest):
    def test_horometro_final_menor_se_rechaza_con_400_y_no_guarda_nada(self):
        self.entrar(self.tecnico)
        doc = self.documento(respuestas={"horometro_inicial": 1200, "horometro_final": 1100, "nivel_aceite_ok": True})
        r = self.sincronizar(doc)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(any("debe ser mayor que" in e for e in r.json()["errores"]))
        self.assertEqual(RegistroMantencion.objects.count(), 0)
        self.assertEqual(self.repo.ids_formularios(), set())
        self.assertTrue(Auditoria.objects.filter(accion=aud.MANTENCION_RECHAZADA).exists())

    def test_json_con_campos_o_tipos_incorrectos_se_rechaza(self):
        self.entrar(self.tecnico)
        r = self.sincronizar(self.documento(respuestas={"horometro_inicial": "mucho", "horometro_final": 5}))
        self.assertEqual(r.status_code, 400)

    def test_cuerpo_que_no_es_json(self):
        self.entrar(self.tecnico)
        r = self.client.post("/api/v1/mantenciones/sincronizar/", data="no es json", content_type="application/json")
        self.assertEqual(r.status_code, 400)


class CP08_AccesoDeTecnicoExterno(BaseTest):
    """Un técnico externo solo ve los equipos que se le asignaron; lo demás da 403 y queda auditado."""

    def test_no_puede_abrir_un_equipo_no_asignado(self):
        self.entrar(self.externo)
        self.assertEqual(self.client.get(reverse("inventario:detalle", args=[self.ups.pk])).status_code, 200)
        r = self.client.get(reverse("inventario:detalle", args=[self.gen.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Auditoria.objects.filter(accion=aud.ACCESO_DENEGADO, usuario=self.externo, entidad="equipo", entidad_id=str(self.gen.pk)).exists())

    def test_no_puede_sincronizar_mantenciones_de_un_equipo_ajeno(self):
        self.entrar(self.externo)
        r = self.sincronizar(self.documento(usuario=self.externo, equipo=self.gen))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(RegistroMantencion.objects.count(), 0)
        self.assertTrue(Auditoria.objects.filter(accion=aud.ACCESO_DENEGADO, usuario=self.externo).exists())

    def test_el_listado_solo_incluye_sus_equipos(self):
        self.entrar(self.externo)
        r = self.client.get(reverse("inventario:lista"))
        self.assertContains(r, self.ups.codigo)
        self.assertNotContains(r, self.gen.codigo)

    def test_no_puede_sincronizar_a_nombre_de_otro_tecnico(self):
        self.entrar(self.tecnico)
        r = self.sincronizar(self.documento(usuario=self.tecnico2))
        self.assertEqual(r.status_code, 403)

    def test_paquete_solo_trae_equipos_visibles(self):
        self.entrar(self.externo)
        datos = self.client.get("/api/v1/paquete/").json()
        self.assertEqual([e["codigo"] for e in datos["equipos"]], [self.ups.codigo])

    def test_tecnico_interno_no_ve_equipos_de_otra_sucursal(self):
        self.entrar(self.tecnico)
        self.assertEqual(self.client.get(reverse("inventario:detalle", args=[self.gen_otra.pk])).status_code, 403)

    def test_trabajador_no_accede_a_plantillas_ni_a_la_auditoria(self):
        self.entrar(self.trabajador)
        self.assertEqual(self.client.get(reverse("mantenciones:plantillas")).status_code, 403)
        self.assertEqual(self.client.get(reverse("auditoria:lista")).status_code, 403)

    def test_la_api_de_tecnicos_rechaza_a_la_jefatura(self):
        self.entrar(self.jefa)
        self.assertEqual(self.client.get("/api/v1/paquete/").status_code, 403)


class CP09_VideoMayorA30Segundos(BaseTest):
    def test_video_de_45_segundos_se_rechaza_y_se_elimina_de_cloudinary(self):
        self.entrar(self.tecnico)
        largo = self.video("video-largo", duracion=45)
        r = self.sincronizar(self.documento(evidencias=[self.foto("f-1"), largo]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(RegistroMantencion.objects.count(), 0)
        self.assertIn("video-largo", self.nube.eliminados)

    def test_el_celular_no_puede_mentir_sobre_la_duracion(self):
        """Dice 10 s, pero Cloudinary informa 45 s: manda lo que informa Cloudinary."""
        self.entrar(self.tecnico)
        evidencia = self.video("video-mentiroso", duracion=45)
        evidencia["duracion_seg"] = 10
        r = self.sincronizar(self.documento(evidencias=[self.foto("f-2"), evidencia]))
        self.assertEqual(r.status_code, 400)

    def test_video_de_30_segundos_se_acepta(self):
        self.entrar(self.tecnico)
        r = self.sincronizar(self.documento(evidencias=[self.foto("f-3"), self.video("video-ok", duracion=30)]))
        self.assertEqual(r.status_code, 201)
        guardado = self.repo.obtener_formulario(json.loads(r.content)["id"])
        self.assertEqual(len(guardado["evidencias"]), 2)

    def test_archivo_que_no_existe_en_cloudinary_se_rechaza(self):
        self.entrar(self.tecnico)
        falsa = {"campo": "foto_equipo", "tipo": "foto", "url": self.nube.prefijo_url + "image/upload/x.jpg", "public_id": "no-existe", "peso_kb": 10}
        self.assertEqual(self.sincronizar(self.documento(evidencias=[falsa])).status_code, 400)

    def test_url_de_otro_almacenamiento_se_rechaza(self):
        self.entrar(self.tecnico)
        ajena = {**self.foto("f-4"), "url": "https://sitio-malicioso.com/a.jpg"}
        self.assertEqual(self.sincronizar(self.documento(evidencias=[ajena])).status_code, 400)

    def test_foto_demasiado_pesada(self):
        self.entrar(self.tecnico)
        pesada = self.foto("f-pesada", bytes_=11 * 1024 * 1024)
        self.assertEqual(self.sincronizar(self.documento(evidencias=[pesada])).status_code, 400)
