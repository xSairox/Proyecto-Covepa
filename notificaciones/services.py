"""Avisos por rol (HU-09): mantenciones programadas y vencidas, tickets por aprobar o asignados."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.permisos import JEFATURA, TECNICO_EXTERNO, TECNICO_INTERNO
from notificaciones.models import Notificacion

DIAS_AVISO_PREVIO = 2


def notificar(usuarios, texto: str, url: str = "", clave: str = "") -> int:
    """Crea un aviso para cada usuario activo. Si `clave` ya existe para ese usuario, no lo repite."""
    creadas = 0
    for usuario in {u.pk: u for u in usuarios if u is not None and u.is_active}.values():
        try:
            with transaction.atomic():
                Notificacion.objects.create(usuario=usuario, texto=texto[:200], url=url[:200], clave=clave[:80])
            creadas += 1
        except IntegrityError:
            continue  # ya se había avisado
    return creadas


def usuarios_de_perfil(codigo: str, sucursal_id: int | None = None):
    from cuentas.models import Usuario

    qs = Usuario.objects.filter(perfil__codigo=codigo, is_active=True)
    if sucursal_id:
        qs = qs.filter(sucursal_id=sucursal_id) | qs.filter(sucursal__isnull=True)
    return qs


def notificar_perfil(codigo: str, texto: str, url: str = "", clave: str = "", sucursal_id: int | None = None) -> int:
    return notificar(usuarios_de_perfil(codigo, sucursal_id), texto, url, clave)


def generar_vencimientos(hoy=None) -> int:
    """Revisa los planes activos y avisa a técnicos y jefatura. Se ejecuta a diario (Vercel Cron)."""
    from django.urls import reverse

    from mantenciones.models import PlanMantencion

    hoy = hoy or timezone.localdate()
    total = 0
    planes = PlanMantencion.objects.filter(activo=True).exclude(equipo__estado="Baja").select_related("equipo", "equipo__sucursal")
    for plan in planes:
        dias = (plan.proxima_fecha() - hoy).days
        if dias > DIAS_AVISO_PREVIO:
            continue
        equipo = plan.equipo
        vencida = dias < 0
        etiqueta = "vencida" if vencida else "proxima"
        clave = f"plan-{plan.pk}-{plan.proxima_fecha():%Y%m%d}-{etiqueta}"
        if vencida:
            texto = f"Mantención vencida: {plan.actividad} en {equipo.codigo} (hace {-dias} días)."
        elif dias == 0:
            texto = f"Mantención para hoy: {plan.actividad} en {equipo.codigo}."
        else:
            texto = f"Mantención programada en {dias} día(s): {plan.actividad} en {equipo.codigo}."
        url = reverse("inventario:detalle", args=[equipo.pk])
        destinatarios = list(usuarios_de_perfil(TECNICO_INTERNO, equipo.sucursal_id))
        destinatarios += list(equipo.tecnicos_externos.filter(perfil__codigo=TECNICO_EXTERNO))
        destinatarios += list(usuarios_de_perfil(JEFATURA, equipo.sucursal_id))
        total += notificar(destinatarios, texto, url, clave)
    return total
