"""Seguridad (informe, sección 8): auditoría inmutable, sesiones por perfil, dos pasos, enlaces de un solo uso."""

from datetime import timedelta

import pyotp
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from auditoria import services as aud
from auditoria.models import Auditoria
from cuentas import services as cuentas
from cuentas.models import TokenAcceso
from pruebas.base import CLAVE, BaseTest


class AuditoriaInmutable(BaseTest):
    def setUp(self):
        super().setUp()
        self.evento = aud.registrar(self.jefa, aud.USUARIO_EDITADO, "usuario", self.tecnico.pk, {"campo": "nombre"})

    def test_no_se_puede_modificar_un_evento(self):
        self.evento.accion = "otra"
        with self.assertRaises(PermissionError):
            self.evento.save()

    def test_no_se_puede_eliminar_un_evento(self):
        with self.assertRaises(PermissionError):
            self.evento.delete()

    def test_no_se_permiten_update_ni_delete_masivos(self):
        with self.assertRaises(PermissionError):
            Auditoria.objects.all().update(accion="x")
        with self.assertRaises(PermissionError):
            Auditoria.objects.all().delete()
        self.assertTrue(Auditoria.objects.filter(pk=self.evento.pk).exists())

    def test_el_auditor_solo_puede_leer(self):
        self.entrar(self.auditor)
        r = self.client.get(reverse("auditoria:lista"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post(reverse("auditoria:lista"), {"accion": "x"}).status_code, 405)

    def test_login_exitoso_y_fallido_quedan_registrados(self):
        self.client.post(reverse("cuentas:login"), {"correo": self.tecnico.correo, "password": "mala-clave-1"})
        self.client.post(reverse("cuentas:login"), {"correo": self.tecnico.correo, "password": CLAVE})
        acciones = set(Auditoria.objects.filter(usuario=self.tecnico).values_list("accion", flat=True))
        self.assertTrue({aud.LOGIN_FALLIDO, aud.LOGIN_OK} <= acciones)

    def test_un_fallo_al_auditar_no_tumba_la_operacion(self):
        from unittest import mock

        with mock.patch("auditoria.models.Auditoria.objects") as falso:
            falso.create.side_effect = RuntimeError("bd no disponible")
            self.assertIsNone(aud.registrar(self.jefa, aud.LOGIN_OK, "usuario", 1))


class SesionesPorPerfil(BaseTest):
    def test_tecnico_12_horas_resto_30_minutos(self):
        self.entrar(self.tecnico)
        self.client.get("/mantenciones/inicio/")
        self.assertEqual(self.client.session.get_expiry_age(), 12 * 3600)
        otro = self.entrar(self.trabajador, Client())
        otro.get("/tickets/")
        self.assertEqual(otro.session.get_expiry_age(), 30 * 60)

    def test_cabeceras_de_seguridad(self):
        r = self.client.get(reverse("cuentas:login"))
        csp = r.headers["Content-Security-Policy"]
        script = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
        self.assertEqual(script.strip(), "script-src 'self'")  # sin scripts en línea ni de terceros
        self.assertIn("frame-ancestors 'none'", csp)

    def test_cerrar_sesion_requiere_post(self):
        self.entrar(self.tecnico)
        self.assertEqual(self.client.get(reverse("cuentas:logout")).status_code, 405)
        self.client.post(reverse("cuentas:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_paginas_privadas_redirigen_al_login(self):
        for ruta in ("/", "/equipos/", "/tickets/", "/mantenciones/inicio/", "/auditoria/"):
            r = self.client.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/cuentas/login/", r["Location"])

    def test_login_no_redirige_a_sitios_externos(self):
        r = self.client.post(reverse("cuentas:login") + "?next=https://malo.example/", {"correo": self.tecnico.correo, "password": CLAVE})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(r["Location"].startswith("http"))


class DosPasos(BaseTest):
    def test_jefatura_sin_segundo_paso_no_accede_a_nada(self):
        self.client.force_login(self.jefa)  # sin otp_verificado
        for ruta in ("/equipos/", "/cuentas/usuarios/", "/auditoria/"):
            r = self.client.get(ruta)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertIn("/cuentas/2fa/", r["Location"])

    def test_el_tecnico_no_necesita_segundo_paso(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get("/mantenciones/inicio/").status_code, 200)

    def test_configurar_y_verificar_codigo(self):
        self.client.force_login(self.jefa)
        r = self.client.get(reverse("cuentas:dos_pasos"))
        self.assertRedirects(r, reverse("cuentas:dos_pasos_configurar"), fetch_redirect_response=False)
        self.client.get(reverse("cuentas:dos_pasos_configurar"))
        self.jefa.refresh_from_db()
        secreto = self.jefa.secreto_totp()
        self.assertNotEqual(self.jefa.totp_secreto, secreto)  # se guarda cifrado
        malo = self.client.post(reverse("cuentas:dos_pasos_configurar"), {"codigo": "000000"})
        self.assertEqual(malo.status_code, 200)
        ok = self.client.post(reverse("cuentas:dos_pasos_configurar"), {"codigo": pyotp.TOTP(secreto).now()})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(self.client.get("/equipos/").status_code, 200)
        self.assertTrue(Auditoria.objects.filter(accion=aud.DOS_PASOS_ACTIVADO, usuario=self.jefa).exists())

    def test_codigos_incorrectos_repetidos_bloquean_la_cuenta(self):
        cuentas.asegurar_secreto_totp(self.auditor)
        self.auditor.dos_pasos_activo = True
        self.auditor.save()
        self.client.force_login(self.auditor)
        for _ in range(5):
            self.client.post(reverse("cuentas:dos_pasos"), {"codigo": "123456"})
        self.auditor.refresh_from_db()
        self.assertTrue(self.auditor.esta_bloqueado())
        self.assertNotIn("_auth_user_id", self.client.session)


class EnlacesDeAcceso(BaseTest):
    def test_invitacion_de_un_solo_uso_y_con_politica_de_clave(self):
        token, _ = TokenAcceso.emitir(self.tecnico, TokenAcceso.INVITACION)
        url = reverse("cuentas:activar", args=[token])
        self.assertEqual(self.client.get(url).status_code, 200)
        corta = self.client.post(url, {"new_password1": "abc123", "new_password2": "abc123"})
        self.assertEqual(corta.status_code, 200)  # rechazada por la política
        solo_letras = self.client.post(url, {"new_password1": "sololetrasaqui", "new_password2": "sololetrasaqui"})
        self.assertEqual(solo_letras.status_code, 200)
        ok = self.client.post(url, {"new_password1": "NuevaClave2026", "new_password2": "NuevaClave2026"})
        self.assertEqual(ok.status_code, 302)
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.check_password("NuevaClave2026"))
        self.assertEqual(self.client.get(url).status_code, 410)  # ya fue usado

    def test_enlace_vencido_o_inventado(self):
        token, objeto = TokenAcceso.emitir(self.tecnico, TokenAcceso.INVITACION)
        objeto.expira = timezone.now() - timedelta(minutes=1)
        objeto.save()
        self.assertEqual(self.client.get(reverse("cuentas:activar", args=[token])).status_code, 410)
        self.assertEqual(self.client.get(reverse("cuentas:activar", args=["inventado"])).status_code, 410)

    def test_un_enlace_nuevo_invalida_el_anterior(self):
        viejo, _ = TokenAcceso.emitir(self.tecnico, TokenAcceso.RECUPERACION)
        TokenAcceso.emitir(self.tecnico, TokenAcceso.RECUPERACION)
        self.assertEqual(self.client.get(reverse("cuentas:recuperar_confirmar", args=[viejo])).status_code, 410)

    def test_el_token_no_se_guarda_en_claro(self):
        token, objeto = TokenAcceso.emitir(self.tecnico, TokenAcceso.INVITACION)
        self.assertNotIn(token, objeto.token_hash)
        self.assertEqual(len(objeto.token_hash), 64)

    def test_recuperar_responde_igual_exista_o_no_el_correo(self):
        r1 = self.client.post(reverse("cuentas:recuperar"), {"correo": self.tecnico.correo}, follow=True)
        r2 = self.client.post(reverse("cuentas:recuperar"), {"correo": "nadie@covepa.cl"}, follow=True)
        self.assertEqual([str(m) for m in r1.context["messages"]], [str(m) for m in r2.context["messages"]])
        self.assertEqual(len(mail.outbox), 1)  # solo salió el correo de la cuenta real

    def test_un_enlace_de_invitacion_no_sirve_para_recuperar(self):
        token, _ = TokenAcceso.emitir(self.tecnico, TokenAcceso.INVITACION)
        self.assertEqual(self.client.get(reverse("cuentas:recuperar_confirmar", args=[token])).status_code, 410)
