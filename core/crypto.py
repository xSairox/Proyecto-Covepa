"""Cifrado simétrico (Fernet) para secretos que no se pueden guardar con hash, como el secreto TOTP."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    clave = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not clave:
        clave = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(clave.encode() if isinstance(clave, str) else clave)


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
