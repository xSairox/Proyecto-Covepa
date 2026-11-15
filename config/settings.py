"""Configuración de Django para COVEPA Mantenciones.

Toda la configuración sensible llega por variables de entorno (ver .env.example).
Servicios en la nube:
  - PostgreSQL ........ Neon (cadena "pooled" en runtime, cadena directa para migrar)
  - MongoDB ........... MongoDB Atlas (pymongo)
  - Fotos y videos .... Cloudinary (subida directa desde el celular con firma del servidor)
  - Hosting ........... Vercel (WSGI + WhiteNoise para estáticos)
"""

import logging
import os
import sys
from pathlib import Path

import dj_database_url

try:  # carga .env en desarrollo; en Vercel las variables ya vienen en el entorno
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nombre: str, defecto: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_lista(nombre: str, defecto: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


DEBUG = env_bool("DEBUG", False)
TESTING = "test" in sys.argv
BUILD = "collectstatic" in sys.argv  # Vercel ejecuta collectstatic durante el build

# --------------------------------------------------------------------------- seguridad
# Variables obligatorias en producción que no están definidas. Importar la configuración NO falla
# (Vercel ejecuta manage.py para detectar el proyecto), pero config/wsgi.py y config/asgi.py se
# niegan a arrancar el servidor mientras esta lista no esté vacía.
FALTAN_VARIABLES: list[str] = []

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = "inseguro-solo-para-desarrollo-no-usar-en-produccion"  # noqa: S105
    if not (DEBUG or TESTING or BUILD):
        FALTAN_VARIABLES.append("SECRET_KEY")

ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS", ".vercel.app,localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_lista("CSRF_TRUSTED_ORIGINS", "https://*.vercel.app")
FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")

if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
CSRF_FAILURE_VIEW = "core.views.csrf_fallo"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Políticas del informe (secciones 8.2 y 8.4)
POLITICAS = {
    "MAX_INTENTOS": 5,            # intentos fallidos antes de bloquear
    "BLOQUEO_MIN": 15,            # minutos de bloqueo de la cuenta
    "SESION_STAFF_MIN": 30,       # jefatura, auditor y trabajador: cierre por inactividad
    "SESION_TECNICO_HORAS": 12,   # técnicos: dura la jornada
    "INVITACION_HORAS": 24,       # enlace de activación de cuenta nueva
    "RECUPERACION_HORAS": 1,      # enlace de recuperación de contraseña
    "CLAVE_MIN_LARGO": 10,
    "VIDEO_MAX_SEG": 30,          # videos de hasta 30 segundos
    "FOTO_MAX_MB": 10,
    "VIDEO_MAX_MB": 100,
    "RETENCION_AUDITORIA_ANIOS": 2,
}

# --------------------------------------------------------------------------- aplicaciones
INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "cuentas",
    "inventario",
    "mantenciones",
    "tickets",
    "notificaciones",
    "auditoria",
]

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")
CLOUDINARY_FOLDER = os.environ.get("CLOUDINARY_FOLDER", "covepa/mantenciones")
CLOUDINARY_ENABLED = bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)

if CLOUDINARY_ENABLED:
    # django-cloudinary-storage debe ir antes de django.contrib.staticfiles.
    INSTALLED_APPS.insert(INSTALLED_APPS.index("django.contrib.staticfiles"), "cloudinary_storage")
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
        "API_KEY": CLOUDINARY_API_KEY,
        "API_SECRET": CLOUDINARY_API_SECRET,
        "SECURE": True,
    }

AUTH_USER_MODEL = "cuentas.Usuario"
AUTHENTICATION_BACKENDS = ["cuentas.backends.CorreoBackend"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CabecerasSeguridadMiddleware",
    "core.middleware.PerfilSesionMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.navegacion",
            ],
        },
    },
]

# --------------------------------------------------------------------------- PostgreSQL (Neon)


def _configurar_base_relacional() -> dict:
    url = os.environ.get("DATABASE_URL", "")
    # Las migraciones deben ir por la conexión directa (el pooler de Neon usa PgBouncer).
    # Solo si también hay DATABASE_URL: sin ella se trabaja en local con SQLite.
    if url and "migrate" in sys.argv and os.environ.get("DIRECT_DATABASE_URL"):
        url = os.environ["DIRECT_DATABASE_URL"]
    if url:
        config = dj_database_url.parse(
            url,
            conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            conn_health_checks=True,
        )
        # PgBouncer en modo transacción no admite cursores del lado del servidor.
        config["DISABLE_SERVER_SIDE_CURSORS"] = True
        config.setdefault("OPTIONS", {}).setdefault("sslmode", "require")
        return config
    if not (DEBUG or TESTING or BUILD):
        FALTAN_VARIABLES.append("DATABASE_URL")
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}


DATABASES = {"default": _configurar_base_relacional()}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# --------------------------------------------------------------------------- MongoDB (Atlas)
MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "covepa")

# --------------------------------------------------------------------------- contraseñas y sesiones
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": POLITICAS["CLAVE_MIN_LARGO"]},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "cuentas.validators.LetrasYNumerosValidator"},
]
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = POLITICAS["SESION_TECNICO_HORAS"] * 3600  # tope; el middleware ajusta por perfil
SESSION_SAVE_EVERY_REQUEST = True

LOGIN_URL = "cuentas:login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "cuentas:login"

# --------------------------------------------------------------------------- internacionalización
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- archivos
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

if DEBUG or TESTING:
    _static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    _static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"

STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if CLOUDINARY_ENABLED
            else "django.core.files.storage.FileSystemStorage"
        )
    },
    "staticfiles": {"BACKEND": _static_backend},
}

# --------------------------------------------------------------------------- correo
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST and not TESTING
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "COVEPA Mantenciones <no-reply@covepa.cl>")

CRON_SECRET = os.environ.get("CRON_SECRET", "")

# --------------------------------------------------------------------------- registros (logs)
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "simple", "stream": sys.stdout},
    },
    "root": {"handlers": ["consola"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"handlers": ["consola"], "level": "WARNING", "propagate": False},
        "covepa": {"handlers": ["consola"], "level": LOG_LEVEL, "propagate": False},
    },
}
if TESTING:
    logging.disable(logging.CRITICAL)
