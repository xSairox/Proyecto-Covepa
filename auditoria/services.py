"""Registro de eventos de auditoría (informe, 8.2 y 8.4: tabla de solo inserción)."""

from __future__ import annotations

import ipaddress
import logging

from django.db import transaction

logger = logging.getLogger("covepa.auditoria")

# Acciones registradas
LOGIN_OK = "login_ok"
LOGIN_FALLIDO = "login_fallido"
CUENTA_BLOQUEADA = "cuenta_bloqueada"
DOS_PASOS_FALLIDO = "dos_pasos_fallido"
DOS_PASOS_ACTIVADO = "dos_pasos_activado"
LOGOUT = "logout"
ACCESO_DENEGADO = "acceso_denegado"
USUARIO_CREADO = "usuario_creado"
USUARIO_EDITADO = "usuario_editado"
USUARIO_DESACTIVADO = "usuario_desactivado"
CONTRASENA_DEFINIDA = "contrasena_definida"
EQUIPO_CREADO = "equipo_creado"
EQUIPO_EDITADO = "equipo_editado"
EQUIPO_BAJA = "equipo_baja"
VERSION_SOFTWARE = "version_software"
PLANTILLA_PUBLICADA = "plantilla_publicada"
PLAN_GUARDADO = "plan_guardado"
MANTENCION_SINCRONIZADA = "mantencion_sincronizada"
MANTENCION_DUPLICADA = "mantencion_duplicada"
MANTENCION_RECHAZADA = "mantencion_rechazada"
TICKET_CAMBIO_ESTADO = "ticket_cambio_estado"


def _ip(request) -> str | None:
    if request is None:
        return None
    crudo = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(crudo))
    except ValueError:
        return None


def registrar(usuario, accion, entidad, entidad_id=None, detalle=None, request=None):
    """Inserta un evento. Un fallo al auditar se registra en el log pero no rompe la operación."""
    from auditoria.models import Auditoria

    autenticado = bool(getattr(usuario, "is_authenticated", False)) and getattr(usuario, "pk", None)
    try:
        with transaction.atomic():
            return Auditoria.objects.create(
                usuario=usuario if autenticado else None,
                accion=accion,
                entidad=entidad,
                entidad_id="" if entidad_id is None else str(entidad_id),
                detalle=detalle or {},
                ip=_ip(request),
            )
    except Exception:  # noqa: BLE001 - la auditoría no debe tumbar la petición
        logger.exception("No se pudo registrar el evento de auditoría %s", accion)
        return None
