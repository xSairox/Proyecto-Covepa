import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

PREFIJO_RE = RegexValidator(r"^[A-Z]{2,4}$", "Use de 2 a 4 letras mayúsculas (ej. GEN).")
CODIGO_RE = re.compile(r"^[A-Z]{2,4}-[A-Z]{2,4}-\d{2,3}$")


class Sucursal(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_sucursal")
    nombre = models.CharField(max_length=80, unique=True)
    comuna = models.CharField(max_length=80)
    prefijo = models.CharField(max_length=4, unique=True, validators=[PREFIJO_RE], help_text="Ej. FRE para Fresia.")

    class Meta:
        db_table = "sucursal"
        ordering = ["nombre"]
        verbose_name_plural = "sucursales"

    def __str__(self) -> str:
        return self.nombre


class Categoria(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_categoria")
    nombre = models.CharField(max_length=80, unique=True)
    prefijo = models.CharField(max_length=4, unique=True, validators=[PREFIJO_RE], help_text="Ej. GEN para Generadores.")

    class Meta:
        db_table = "categoria"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre


class Equipo(models.Model):
    ACTIVO = "Activo"
    EN_MANTENCION = "En mantención"
    BAJA = "Baja"
    ESTADOS = [(ACTIVO, "Activo"), (EN_MANTENCION, "En mantención"), (BAJA, "Dado de baja")]

    id = models.AutoField(primary_key=True, db_column="id_equipo")
    codigo = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Formato TIPO-SUC-00, por ejemplo GEN-FRE-01. Si lo dejas vacío se asigna el siguiente disponible.",
    )
    nombre = models.CharField(max_length=100)
    marca = models.CharField(max_length=60, blank=True)
    modelo = models.CharField(max_length=60, blank=True)
    ubicacion = models.CharField(max_length=120, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ACTIVO)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, db_column="id_categoria", related_name="equipos")
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT, db_column="id_sucursal", related_name="equipos")
    tecnicos_externos = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="equipos_asignados",
        db_table="equipo_tecnico_externo",
        help_text="Técnicos externos que pueden ver y mantener este equipo.",
    )
    fecha_alta = models.DateField(default=timezone.localdate)
    fecha_baja = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "equipo"
        ordering = ["codigo"]
        indexes = [models.Index(fields=["sucursal", "estado"])]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.nombre}"

    @staticmethod
    def siguiente_codigo(categoria: Categoria, sucursal: Sucursal) -> str:
        base = f"{categoria.prefijo}-{sucursal.prefijo}-"
        existentes = Equipo.objects.filter(codigo__startswith=base).values_list("codigo", flat=True)
        numeros = [int(c[len(base):]) for c in existentes if c[len(base):].isdigit()]
        return f"{base}{(max(numeros) + 1) if numeros else 1:02d}"

    def clean(self):
        self.codigo = (self.codigo or "").strip().upper()
        if self.codigo and not CODIGO_RE.match(self.codigo):
            raise ValidationError({"codigo": "El código debe tener el formato TIPO-SUC-00 (ej. GEN-FRE-01)."})

    def save(self, *args, **kwargs):
        if not self.codigo and self.categoria_id and self.sucursal_id:
            self.codigo = self.siguiente_codigo(self.categoria, self.sucursal)
        self.codigo = (self.codigo or "").upper()
        super().save(*args, **kwargs)

    @property
    def esta_de_baja(self) -> bool:
        return self.estado == self.BAJA

    def dar_de_baja(self) -> None:
        """El equipo no se elimina: cambia de estado y conserva todo su historial (HU-02)."""
        self.estado = self.BAJA
        self.fecha_baja = timezone.localdate()
        self.save(update_fields=["estado", "fecha_baja"])
        self.planes.update(activo=False)

    def delete(self, *args, **kwargs):
        raise PermissionError("Los equipos no se eliminan; use dar_de_baja() para conservar el historial.")


class VersionSoftware(models.Model):
    FIRMWARE = "firmware"
    SOFTWARE = "software"
    TIPOS = [(FIRMWARE, "Firmware"), (SOFTWARE, "Software")]

    id = models.AutoField(primary_key=True, db_column="id_version")
    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, db_column="id_equipo", related_name="versiones")
    tipo = models.CharField(max_length=10, choices=TIPOS, default=FIRMWARE)
    version = models.CharField(max_length=40)
    fecha = models.DateField(default=timezone.localdate)
    actual = models.BooleanField(default=True)

    class Meta:
        db_table = "version_software"
        ordering = ["-fecha", "-id"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.version}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.actual:  # solo una versión vigente por tipo; las anteriores quedan en el historial
                VersionSoftware.objects.filter(equipo=self.equipo, tipo=self.tipo, actual=True).exclude(pk=self.pk).update(
                    actual=False
                )
            super().save(*args, **kwargs)
