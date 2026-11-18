import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.crypto import cifrar, descifrar
from core.permisos import JEFATURA, PERFILES, PERFILES_2FA


class Perfil(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_perfil")
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=60)
    permisos = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "perfil"
        ordering = ["id"]

    def __str__(self) -> str:
        return self.nombre

    @property
    def requiere_dos_pasos(self) -> bool:
        return self.codigo in PERFILES_2FA


class UsuarioManager(BaseUserManager):
    def _crear(self, correo, password, **extra):
        if not correo:
            raise ValueError("El correo es obligatorio.")
        usuario = self.model(correo=self.normalize_email(correo).lower(), **extra)
        if password:
            usuario.set_password(password)
        else:
            usuario.set_unusable_password()
        usuario.save(using=self._db)
        return usuario

    def create_user(self, correo, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(correo, password, **extra)

    def create_superuser(self, correo, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if "perfil" not in extra and "perfil_id" not in extra:
            datos = PERFILES[JEFATURA]
            extra["perfil"], _ = Perfil.objects.get_or_create(
                codigo=JEFATURA, defaults={"nombre": datos["nombre"], "permisos": datos["permisos"]}
            )
        return self._crear(correo, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Usuario del sistema. Se identifica con un ID interno y el correo; no se usa el RUT."""

    id = models.AutoField(primary_key=True, db_column="id_usuario")
    nombre = models.CharField(max_length=60)
    apellido = models.CharField(max_length=60)
    correo = models.EmailField(max_length=120, unique=True)
    perfil = models.ForeignKey(Perfil, on_delete=models.PROTECT, db_column="id_perfil", related_name="usuarios")
    sucursal = models.ForeignKey(
        "inventario.Sucursal",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_column="id_sucursal",
        related_name="usuarios",
    )
    empresa_externa = models.CharField(max_length=100, blank=True, help_text="Solo para técnicos externos.")
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField(default=False)
    dos_pasos_activo = models.BooleanField(default=False)
    totp_secreto = models.CharField(max_length=200, blank=True, help_text="Secreto TOTP cifrado.")
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS = ["nombre", "apellido"]

    class Meta:
        db_table = "usuario"
        ordering = ["apellido", "nombre"]

    def __str__(self) -> str:
        return self.get_full_name()

    def save(self, *args, **kwargs):
        self.correo = (self.correo or "").strip().lower()
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()

    def get_short_name(self) -> str:
        return self.nombre

    @property
    def codigo_perfil(self) -> str:
        return self.perfil.codigo

    def tiene_permiso(self, permiso: str) -> bool:
        return self.is_active and permiso in (self.perfil.permisos or [])

    # --- bloqueo por intentos fallidos -------------------------------------------------
    def esta_bloqueado(self) -> bool:
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    # --- segundo factor ----------------------------------------------------------------
    def guardar_secreto_totp(self, secreto: str) -> None:
        self.totp_secreto = cifrar(secreto)

    def secreto_totp(self) -> str:
        return descifrar(self.totp_secreto) if self.totp_secreto else ""

    # --- ciclo de vida -----------------------------------------------------------------
    def desactivar(self) -> None:
        """Desactiva la cuenta y cierra todas sus sesiones (celular perdido, fin de contrato externo)."""
        self.is_active = False
        self.save(update_fields=["is_active"])
        self.cerrar_sesiones()

    def cerrar_sesiones(self) -> int:
        from django.contrib.sessions.models import Session

        cerradas = 0
        for sesion in Session.objects.filter(expire_date__gt=timezone.now()):
            if sesion.get_decoded().get("_auth_user_id") == str(self.pk):
                sesion.delete()
                cerradas += 1
        return cerradas


class TokenAcceso(models.Model):
    """Enlace de un solo uso para definir la contraseña (invitación o recuperación)."""

    INVITACION = "invitacion"
    RECUPERACION = "recuperacion"
    TIPOS = [(INVITACION, "Invitación"), (RECUPERACION, "Recuperación de contraseña")]

    id = models.AutoField(primary_key=True, db_column="id_token")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tokens")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    token_hash = models.CharField(max_length=64, unique=True)
    creado = models.DateTimeField(default=timezone.now)
    expira = models.DateTimeField()
    usado = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "token_acceso"

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def emitir(cls, usuario, tipo: str):
        """Crea un token nuevo e invalida los anteriores sin usar. Devuelve (token_en_claro, objeto)."""
        horas = (
            settings.POLITICAS["INVITACION_HORAS"] if tipo == cls.INVITACION else settings.POLITICAS["RECUPERACION_HORAS"]
        )
        cls.objects.filter(usuario=usuario, tipo=tipo, usado__isnull=True).update(usado=timezone.now())
        token = secrets.token_urlsafe(32)
        objeto = cls.objects.create(
            usuario=usuario, tipo=tipo, token_hash=cls._hash(token), expira=timezone.now() + timedelta(hours=horas)
        )
        return token, objeto

    @classmethod
    def buscar_vigente(cls, token: str, tipo: str):
        try:
            objeto = cls.objects.select_related("usuario").get(token_hash=cls._hash(token), tipo=tipo)
        except cls.DoesNotExist:
            return None
        if objeto.usado or objeto.expira <= timezone.now() or not objeto.usuario.is_active:
            return None
        return objeto

    def consumir(self) -> None:
        self.usado = timezone.now()
        self.save(update_fields=["usado"])
