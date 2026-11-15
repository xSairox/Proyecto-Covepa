"""Tickets de mantención correctiva (HU-06, HU-07, HU-08) y avisos (HU-09)."""

import json
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from auditoria import services as aud
from auditoria.models import Auditoria
from mantenciones.models import PlanMantencion
from notificaciones.models import Notificacion
from notificaciones.services import generar_vencimientos
from pruebas.base import BaseTest
from tickets import estados, services
from tickets.models import DocumentoRespaldo, Material, Ticket


class FlujoDeTicket(BaseTest):
    def nuevo(self, equipo=None):
        return services.crear_ticket(self.trabajador, Ticket.FALLA, "El generador no arranca", equipo or self.gen)

    def test_flujo_completo_con_historial_y_avisos(self):
        t = self.nuevo()
        self.assertEqual(t.estado, estados.PENDIENTE)
        self.assertTrue(Notificacion.objects.filter(usuario=self.jefa, texto__contains=t.numero).exists())

        services.aprobar(t, self.jefa, self.tecnico)
        self.assertEqual((t.estado, t.tecnico), (estados.APROBADO, self.tecnico))
        self.assertTrue(Notificacion.objects.filter(usuario=self.tecnico, texto__contains="asignó").exists())

        services.iniciar(t, self.tecnico)
        self.assertIsNotNone(t.inicio_trabajo)

        url = self.nube.registrar("factura-1", "foto")
        services.realizar(
            t, self.tecnico,
            [{"descripcion": "Filtro de aceite", "cantidad": "2", "unidad": "u"}],
            [{"tipo": "factura", "numero": "F-123", "proveedor": "Repuestos Sur", "monto": "45900", "public_id": "factura-1", "url": url}],
            "Se cambió el filtro",
        )
        self.assertEqual(t.estado, estados.REALIZADO)
        self.assertEqual(Material.objects.filter(ticket=t).count(), 1)
        self.assertEqual(DocumentoRespaldo.objects.get(ticket=t).monto, 45900)

        services.cerrar(t, self.jefa)
        self.assertEqual(t.estado, estados.CERRADO)
        self.assertEqual([h.estado for h in t.historial.order_by("fecha", "pk")], ["Pendiente", "Aprobado", "En ejecución", "Realizado", "Cerrado"])
        self.assertTrue(Notificacion.objects.filter(usuario=self.trabajador, texto__contains="cerrado").exists())

    def test_la_jefatura_puede_devolver_el_trabajo_al_tecnico(self):
        t = self.nuevo()
        services.aprobar(t, self.jefa, self.tecnico)
        services.iniciar(t, self.tecnico)
        services.realizar(t, self.tecnico, [], [], "")
        services.devolver(t, self.jefa, "Falta la factura del filtro")
        self.assertEqual(t.estado, estados.EN_EJECUCION)
        self.assertIsNone(t.termino_trabajo)
        with self.assertRaises(ValidationError):
            services.devolver(t, self.jefa, "otra vez")  # ya no está Realizado

    def test_rechazo_exige_motivo_y_es_final(self):
        t = self.nuevo()
        with self.assertRaises(ValidationError):
            services.rechazar(t, self.jefa, "  ")
        services.rechazar(t, self.jefa, "No corresponde a COVEPA")
        self.assertEqual(t.estado, estados.RECHAZADO)
        with self.assertRaises(ValidationError):
            services.aprobar(t, self.jefa, self.tecnico)

    def test_no_se_pueden_saltar_estados(self):
        t = self.nuevo()
        with self.assertRaises((ValidationError, PermissionDenied)):
            services.iniciar(t, self.tecnico)  # no es el asignado y aún no está aprobado
        with self.assertRaises(ValidationError):
            services.cerrar(t, self.jefa)

    def test_solo_el_tecnico_asignado_ejecuta_y_queda_auditado(self):
        t = self.nuevo()
        services.aprobar(t, self.jefa, self.tecnico)
        with self.assertRaises(PermissionDenied):
            services.iniciar(t, self.tecnico2)
        self.assertTrue(Auditoria.objects.filter(accion=aud.ACCESO_DENEGADO, usuario=self.tecnico2, entidad="ticket").exists())

    def test_solo_la_jefatura_aprueba_y_cierra(self):
        t = self.nuevo()
        for actor in (self.tecnico, self.trabajador, self.auditor):
            with self.assertRaises(PermissionDenied):
                services.aprobar(t, actor, self.tecnico)

    def test_el_tecnico_elegido_debe_corresponder_al_equipo(self):
        t = self.nuevo()  # generador de Fresia
        with self.assertRaises(ValidationError):
            services.aprobar(t, self.jefa, self.externo)  # el externo solo tiene asignada la UPS
        t2 = self.nuevo(self.ups)
        services.aprobar(t2, self.jefa, self.externo)
        self.assertEqual(t2.tecnico, self.externo)

    def test_el_trabajador_no_puede_reportar_fallas_de_equipos_que_no_ve(self):
        with self.assertRaises(PermissionDenied):
            services.crear_ticket(self.trabajador, Ticket.FALLA, "falla", self.gen_otra)

    def test_documento_de_respaldo_debe_existir_en_cloudinary(self):
        t = self.nuevo()
        services.aprobar(t, self.jefa, self.tecnico)
        services.iniciar(t, self.tecnico)
        falso = [{"tipo": "factura", "numero": "1", "proveedor": "x", "monto": 1, "public_id": "fantasma", "url": self.nube.prefijo_url + "x.jpg"}]
        with self.assertRaises(ValidationError):
            services.realizar(t, self.tecnico, [], falso, "")
        t.refresh_from_db()
        self.assertEqual(t.estado, estados.EN_EJECUCION)  # no avanzó

    def test_alcance_de_tickets_por_perfil(self):
        propio = self.nuevo()
        otro = services.crear_ticket(self.usuario("otro@covepa.cl", "trabajador", self.fresia), Ticket.FALLA, "otra falla", self.ups)
        self.assertEqual(set(services.tickets_visibles(self.trabajador)), {propio})
        self.assertEqual(set(services.tickets_visibles(self.jefa)), {propio, otro})
        self.assertEqual(set(services.tickets_visibles(self.externo)), set())


class TicketsPorWeb(BaseTest):
    def test_flujo_por_las_pantallas(self):
        self.entrar(self.trabajador)
        r = self.client.post(reverse("tickets:nuevo"), {"equipo": self.gen.pk, "descripcion": "Hace ruido y no arranca"})
        self.assertEqual(r.status_code, 302)
        t = Ticket.objects.get()

        self.entrar(self.jefa)
        r = self.client.post(reverse("tickets:accion", args=[t.pk, "aprobar"]), {"tecnico": self.tecnico.pk})
        self.assertRedirects(r, reverse("tickets:detalle", args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.estado, estados.APROBADO)

        self.entrar(self.tecnico)
        self.client.post(reverse("tickets:accion", args=[t.pk, "iniciar"]))
        url = self.nube.registrar("fac-web", "foto")
        r = self.client.post(reverse("tickets:accion", args=[t.pk, "realizar"]), {
            "observacion": "Listo",
            "materiales_json": json.dumps([{"descripcion": "Correa", "cantidad": "1", "unidad": "u"}]),
            "documentos_json": json.dumps([{"tipo": "guia_despacho", "numero": "G-9", "proveedor": "Sur", "monto": "", "public_id": "fac-web", "url": url}]),
        })
        t.refresh_from_db()
        self.assertEqual(t.estado, estados.REALIZADO, r.content[:300])

    def test_un_trabajador_ajeno_no_ve_el_ticket(self):
        t = services.crear_ticket(self.trabajador, Ticket.FALLA, "falla", self.gen)
        otro = self.usuario("otro@covepa.cl", "trabajador", self.fresia)
        self.entrar(otro)
        self.assertEqual(self.client.get(reverse("tickets:detalle", args=[t.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("tickets:accion", args=[t.pk, "cerrar"])).status_code, 403)

    def test_accion_desconocida_no_cambia_nada(self):
        t = services.crear_ticket(self.trabajador, Ticket.FALLA, "falla", self.gen)
        self.entrar(self.jefa)
        self.client.post(reverse("tickets:accion", args=[t.pk, "borrar"]))
        t.refresh_from_db()
        self.assertEqual(t.estado, estados.PENDIENTE)

    def test_las_acciones_no_aceptan_get(self):
        t = services.crear_ticket(self.trabajador, Ticket.FALLA, "falla", self.gen)
        self.entrar(self.jefa)
        self.assertEqual(self.client.get(reverse("tickets:accion", args=[t.pk, "aprobar"])).status_code, 405)


class AvisosDeVencimiento(BaseTest):
    def test_plan_vencido_avisa_una_sola_vez_por_dia(self):
        plan = PlanMantencion.objects.create(
            equipo=self.gen, plantilla=self.plantilla, actividad="Prueba semanal", frecuencia_dias=7,
            ultima_fecha=timezone.localdate() - timedelta(days=10),
        )
        creadas = generar_vencimientos()
        self.assertGreaterEqual(creadas, 2)  # técnico interno y jefatura
        self.assertTrue(Notificacion.objects.filter(usuario=self.tecnico, texto__contains="vencida").exists())
        self.assertEqual(generar_vencimientos(), 0)  # idempotente
        self.assertFalse(Notificacion.objects.filter(usuario=self.externo).exists())
        plan.ultima_fecha = timezone.localdate()
        plan.save()
        self.assertEqual(generar_vencimientos(), 0)  # al día: sin avisos nuevos

    def test_el_cron_exige_el_secreto(self):
        from django.test import override_settings

        with override_settings(CRON_SECRET="secreto-de-prueba"):
            self.assertEqual(self.client.get("/cron/vencimientos/").status_code, 401)
            self.assertEqual(self.client.get("/cron/vencimientos/", headers={"Authorization": "Bearer otro"}).status_code, 401)
            ok = self.client.get("/cron/vencimientos/", headers={"Authorization": "Bearer secreto-de-prueba"})
            self.assertEqual(ok.status_code, 200)
        with override_settings(CRON_SECRET=""):
            self.assertEqual(self.client.get("/cron/vencimientos/", headers={"Authorization": "Bearer "}).status_code, 401)
