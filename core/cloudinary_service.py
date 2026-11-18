"""Servicio de Cloudinary: firma de subidas y verificación de archivos.

Flujo (informe, secciones 5.3 y 7.3):
  1. El celular pide una firma al servidor (`firmar_subida`).
  2. El celular sube la foto o el video DIRECTO a Cloudinary (Vercel limita el cuerpo de cada
     petición a ~4,5 MB, así que los archivos nunca pasan por Django).
  3. El celular agrega la URL devuelta al documento JSON y lo envía al servidor.
  4. El servidor verifica con la API de administración de Cloudinary que el archivo existe,
     que está en la carpeta autorizada y que cumple el peso y la duración máximos.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

FORMATOS_PERMITIDOS = "jpg,jpeg,png,webp,heic,mp4,mov,webm"
TIPOS_RESOURCE = {"foto": "image", "video": "video"}


class ActivoInvalido(Exception):
    """El archivo no existe, no es del tipo esperado o excede los límites."""


@dataclass
class ResultadoActivo:
    url: str
    peso_kb: int
    duracion_seg: float | None
    formato: str


def _validar_limites(tipo: str, peso_bytes: int, duracion: float | None, politicas: dict) -> None:
    if tipo == "foto" and peso_bytes > politicas["FOTO_MAX_MB"] * 1024 * 1024:
        raise ActivoInvalido(f"La foto supera los {politicas['FOTO_MAX_MB']} MB permitidos.")
    if tipo == "video":
        if peso_bytes > politicas["VIDEO_MAX_MB"] * 1024 * 1024:
            raise ActivoInvalido(f"El video supera los {politicas['VIDEO_MAX_MB']} MB permitidos.")
        if duracion is None:
            raise ActivoInvalido("No se pudo determinar la duración del video.")
        if duracion > politicas["VIDEO_MAX_SEG"]:
            raise ActivoInvalido(f"El video dura más de {politicas['VIDEO_MAX_SEG']} segundos.")


class CloudinaryReal:
    def __init__(self, cloud_name: str, api_key: str, api_secret: str, carpeta: str, politicas: dict):
        self.cloud_name = cloud_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.carpeta = carpeta.strip("/")
        self.politicas = politicas

    @property
    def prefijo_url(self) -> str:
        return f"https://res.cloudinary.com/{self.cloud_name}/"

    def _configurar(self):
        import cloudinary

        cloudinary.config(
            cloud_name=self.cloud_name, api_key=self.api_key, api_secret=self.api_secret, secure=True
        )
        return cloudinary

    def firmar_subida(self, tipo: str) -> dict:
        """Parámetros firmados para que el celular suba directo a Cloudinary."""
        cloudinary = self._configurar()
        import cloudinary.utils

        if tipo not in TIPOS_RESOURCE:
            raise ActivoInvalido("Tipo de archivo no permitido.")
        params = {
            "timestamp": int(time.time()),
            "folder": self.carpeta,
            "allowed_formats": FORMATOS_PERMITIDOS,
        }
        firma = cloudinary.utils.api_sign_request(params, self.api_secret)
        return {
            "url_subida": f"https://api.cloudinary.com/v1_1/{self.cloud_name}/{TIPOS_RESOURCE[tipo]}/upload",
            "api_key": self.api_key,
            "firma": firma,
            **params,
        }

    def verificar_activo(self, public_id: str, tipo: str) -> ResultadoActivo:
        cloudinary = self._configurar()
        import cloudinary.api
        from cloudinary.exceptions import Error as ErrorCloudinary

        if tipo not in TIPOS_RESOURCE:
            raise ActivoInvalido("Tipo de archivo no permitido.")
        if not public_id.startswith(self.carpeta + "/"):
            raise ActivoInvalido("El archivo no está en la carpeta autorizada.")
        try:
            datos = cloudinary.api.resource(public_id, resource_type=TIPOS_RESOURCE[tipo])
        except ErrorCloudinary as exc:
            raise ActivoInvalido("El archivo no existe en Cloudinary.") from exc
        peso = int(datos.get("bytes", 0))
        duracion = datos.get("duration")
        _validar_limites(tipo, peso, duracion, self.politicas)
        return ResultadoActivo(
            url=datos["secure_url"],
            peso_kb=max(1, peso // 1024),
            duracion_seg=duracion,
            formato=datos.get("format", ""),
        )

    def eliminar(self, public_id: str, tipo: str) -> None:
        cloudinary = self._configurar()
        import cloudinary.uploader

        cloudinary.uploader.destroy(public_id, resource_type=TIPOS_RESOURCE[tipo], invalidate=True)


@dataclass
class CloudinaryFalso:
    """Doble de prueba: no usa red. Los tests registran en `activos` los archivos "subidos"."""

    cloud_name: str = "demo"
    carpeta: str = "covepa/mantenciones"
    politicas: dict = field(
        default_factory=lambda: {"FOTO_MAX_MB": 10, "VIDEO_MAX_MB": 100, "VIDEO_MAX_SEG": 30}
    )
    activos: dict = field(default_factory=dict)
    eliminados: list = field(default_factory=list)

    @property
    def prefijo_url(self) -> str:
        return f"https://res.cloudinary.com/{self.cloud_name}/"

    def firmar_subida(self, tipo: str) -> dict:
        if tipo not in TIPOS_RESOURCE:
            raise ActivoInvalido("Tipo de archivo no permitido.")
        return {
            "url_subida": f"https://api.cloudinary.com/v1_1/{self.cloud_name}/{TIPOS_RESOURCE[tipo]}/upload",
            "api_key": "clave-falsa",
            "firma": "firma-falsa",
            "timestamp": 1,
            "folder": self.carpeta,
            "allowed_formats": FORMATOS_PERMITIDOS,
        }

    def registrar(self, public_id: str, tipo: str, peso_bytes: int = 200_000, duracion: float | None = None):
        self.activos[public_id] = {"tipo": tipo, "bytes": peso_bytes, "duration": duracion}
        return f"{self.prefijo_url}{TIPOS_RESOURCE[tipo]}/upload/v1/{public_id}.jpg"

    def verificar_activo(self, public_id: str, tipo: str) -> ResultadoActivo:
        datos = self.activos.get(public_id)
        if not datos or datos["tipo"] != tipo:
            raise ActivoInvalido("El archivo no existe en Cloudinary.")
        _validar_limites(tipo, datos["bytes"], datos["duration"], self.politicas)
        return ResultadoActivo(
            url=f"{self.prefijo_url}{TIPOS_RESOURCE[tipo]}/upload/v1/{public_id}.jpg",
            peso_kb=max(1, datos["bytes"] // 1024),
            duracion_seg=datos["duration"],
            formato="jpg",
        )

    def eliminar(self, public_id: str, tipo: str) -> None:
        self.eliminados.append(public_id)
        self.activos.pop(public_id, None)


_servicio = None


def obtener_servicio():
    """Servicio configurado. Sin credenciales solo funciona en desarrollo o pruebas (doble falso)."""
    global _servicio
    if _servicio is None:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        if settings.CLOUDINARY_ENABLED:
            _servicio = CloudinaryReal(
                settings.CLOUDINARY_CLOUD_NAME,
                settings.CLOUDINARY_API_KEY,
                settings.CLOUDINARY_API_SECRET,
                settings.CLOUDINARY_FOLDER,
                settings.POLITICAS,
            )
        elif settings.DEBUG or settings.TESTING:
            _servicio = CloudinaryFalso(carpeta=settings.CLOUDINARY_FOLDER, politicas=settings.POLITICAS)
        else:
            raise ImproperlyConfigured("Faltan las credenciales de Cloudinary.")
    return _servicio


def fijar_servicio(servicio) -> None:
    global _servicio
    _servicio = servicio
