"""Reglas de autenticación del informe (sección 8.2): bloqueo, enlaces de acceso y segundo factor."""

from __future__ import annotations

import logging
from datetime import timedelta

import pyotp
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from auditoria import services as auditoria
from cuentas.models import TokenAcceso, Usuario

logger = logging.getLogger("covepa.cuentas")


def registrar_fallo(usuario: Usuario | None, correo: str, request, accion: str = auditoria.LOGIN_FALLIDO) -> bool:
    """Cuenta un intento fallido y bloquea la cuenta al llegar al máximo. Devuelve True si quedó bloqueada."""
    politicas = settings.POLITICAS
    if usuario is None:
        auditoria.registrar(None, accion, "usuario", detalle={"correo": correo[:120]}, request=request)
        return False
    bloqueada = False
    with transaction.atomic():
        u = Usuario.objects.select_for_update().get(pk=usuario.pk)
        u.intentos_fallidos += 1
        if u.intentos_fallidos >= politicas["MAX_INTENTOS"]:
            u.bloqueado_hasta = timezone.now() + timedelta(minutes=politicas["BLOQUEO_MIN"])
            u.intentos_fallidos = 0
            bloqueada = True
        u.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
    auditoria.registrar(
        u,
        auditoria.CUENTA_BLOQUEADA if bloqueada else accion,
        "usuario",
        u.pk,
        detalle={"minutos_bloqueo": politicas["BLOQUEO_MIN"]} if bloqueada else {},
        request=request,
    )
    return bloqueada


def reiniciar_intentos(usuario: Usuario) -> None:
    if usuario.intentos_fallidos or usuario.bloqueado_hasta:
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])


def enviar_enlace(request, usuario: Usuario, tipo: str) -> str:
    """Emite el token, envía el correo y devuelve el enlace (la jefatura lo ve al invitar)."""
    token, _ = TokenAcceso.emitir(usuario, tipo)
    ruta = reverse("cuentas:activar" if tipo == TokenAcceso.INVITACION else "cuentas:recuperar_confirmar", args=[token])
    enlace = request.build_absolute_uri(ruta)
    if tipo == TokenAcceso.INVITACION:
        horas = settings.POLITICAS["INVITACION_HORAS"]
        asunto = "Te invitamos al sistema de mantenciones de COVEPA"
        cuerpo = (
            f"Hola {usuario.nombre},\n\nSe creó tu cuenta. Define tu contraseña en este enlace "
            f"(un solo uso, válido por {horas} horas):\n{enlace}\n\nCOVEPA SpA"
        )
    else:
        horas = settings.POLITICAS["RECUPERACION_HORAS"]
        asunto = "Recupera tu contraseña de COVEPA"
        cuerpo = (
            f"Hola {usuario.nombre},\n\nPuedes definir una contraseña nueva en este enlace "
            f"(un solo uso, válido por {horas} hora):\n{enlace}\n\nSi no lo pediste, ignora este correo."
        )
    try:
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [usuario.correo], fail_silently=False)
    except Exception:  # noqa: BLE001 - el enlace igual se entrega a la jefatura en pantalla
        logger.exception("No se pudo enviar el correo a %s", usuario.correo)
    return enlace


# --- segundo factor (TOTP) ----------------------------------------------------------------------


def uri_totp(usuario: Usuario) -> str:
    return pyotp.TOTP(usuario.secreto_totp()).provisioning_uri(name=usuario.correo, issuer_name="COVEPA Mantenciones")


def asegurar_secreto_totp(usuario: Usuario) -> str:
    if not usuario.totp_secreto:
        usuario.guardar_secreto_totp(pyotp.random_base32())
        usuario.save(update_fields=["totp_secreto"])
    return usuario.secreto_totp()


def verificar_codigo_totp(usuario: Usuario, codigo: str) -> bool:
    codigo = (codigo or "").strip().replace(" ", "")
    if not (codigo.isdigit() and len(codigo) == 6) or not usuario.totp_secreto:
        return False
    return pyotp.TOTP(usuario.secreto_totp()).verify(codigo, valid_window=1)
