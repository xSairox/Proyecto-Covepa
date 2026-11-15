import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.mongo import obtener_repo
from core.validators import validar_definicion_campos
from inventario.models import Categoria, Equipo


class Plantilla(models.Model):
    """Plantilla de formulario por tipo de equipo. Sus campos viven en MongoDB, versionados (HU-03)."""

    id = models.AutoField(primary_key=True, db_column="id_plantilla")
    nombre = models.CharField(max_length=120)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, db_column="id_categoria", related_name="plantillas")
    activa = models.BooleanField(default=True)
    version_actual = models.PositiveIntegerField(default=0, help_text="0 = aún sin versión publicada.")

    class Meta:
        db_table = "plantilla"
        ordering = ["categoria__nombre", "nombre"]
        constraints = [models.UniqueConstraint(fields=["categoria", "nombre"], name="plantilla_nombre_unico_por_categoria")]

    def __str__(self) -> str:
        return f"{self.nombre} (v{self.version_actual})" if self.version_actual else self.nombre

    def publicar_version(self, campos: list[dict]) -> dict:
        """Valida los campos, guarda una versión nueva en MongoDB y la deja como vigente.

        Los registros ya completados conservan la versión que respondieron: las versiones no se modifican.
        """
        campos_validos = validar_definicion_campos(campos)
        doc = obtener_repo().crear_version(self.pk, self.nombre, campos_validos)
        self.version_actual = doc["numero"]
        self.save(update_fields=["version_actual"])
        return doc

    def version(self, numero: int | None = None) -> dict | None:
        return obtener_repo().obtener_version(self.pk, numero or self.version_actual or None)

    def versiones(self) -> list[dict]:
        return obtener_repo().listar_versiones(self.pk)


class PlanMantencion(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_plan")
    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, db_column="id_equipo", related_name="planes")
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, db_column="id_plantilla", related_name="planes")
    actividad = models.CharField(max_length=120)
    frecuencia_dias = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3650)], help_text="Cada cuántos días se repite."
    )
    duracion_min = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    ultima_fecha = models.DateField(null=True, blank=True)
    fecha_creacion = models.DateField(default=timezone.localdate)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "plan_mantencion"
        ordering = ["equipo__codigo", "actividad"]

    def __str__(self) -> str:
        return f"{self.actividad} · {self.equipo.codigo} (cada {self.frecuencia_dias} días)"

    def clean(self):
        if self.equipo_id and self.plantilla_id and self.equipo.categoria_id != self.plantilla.categoria_id:
            raise ValidationError({"plantilla": "La plantilla debe ser de la misma categoría que el equipo."})

    def proxima_fecha(self):
        if self.ultima_fecha:
            return self.ultima_fecha + timedelta(days=self.frecuencia_dias)
        return self.fecha_creacion

    def dias_para_vencer(self, hoy=None) -> int:
        return (self.proxima_fecha() - (hoy or timezone.localdate())).days

    def esta_vencido(self, hoy=None) -> bool:
        return self.dias_para_vencer(hoy) < 0


class RegistroMantencion(models.Model):
    """Datos estructurados de una mantención (para filtrar). El formulario completo vive en MongoDB
    bajo el mismo UUID, generado en el celular."""

    PENDIENTE = "pendiente"
    SINCRONIZADO = "sincronizado"
    ERROR = "error"
    ESTADOS_SYNC = [(PENDIENTE, "Pendiente"), (SINCRONIZADO, "Sincronizado"), (ERROR, "Error")]

    id = models.UUIDField(primary_key=True, db_column="id_documento", default=uuid.uuid4, editable=False)
    equipo = models.ForeignKey(Equipo, on_delete=models.PROTECT, db_column="id_equipo", related_name="registros")
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="id_tecnico", related_name="registros_mantencion"
    )
    plantilla = models.ForeignKey(Plantilla, on_delete=models.PROTECT, db_column="id_plantilla", related_name="registros")
    version_plantilla = models.PositiveIntegerField()
    plan = models.ForeignKey(
        PlanMantencion, null=True, blank=True, on_delete=models.SET_NULL, db_column="id_plan", related_name="registros"
    )
    inicio = models.DateTimeField()
    termino = models.DateTimeField()
    estado_sync = models.CharField(max_length=15, choices=ESTADOS_SYNC, default=SINCRONIZADO)
    origen = models.CharField(max_length=30, default="app_movil")
    sincronizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "registro_mantencion"
        ordering = ["-inicio"]
        indexes = [
            models.Index(fields=["equipo", "-inicio"]),
            models.Index(fields=["tecnico", "-inicio"]),
            models.Index(fields=["-inicio"]),
        ]

    def __str__(self) -> str:
        return f"{self.equipo.codigo} · {self.inicio:%d-%m-%Y %H:%M}"

    @property
    def duracion_min(self) -> int:
        return int((self.termino - self.inicio).total_seconds() // 60)
