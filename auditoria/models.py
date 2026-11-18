from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditoriaQuerySet(models.QuerySet):
    """La auditoría es de solo inserción: se bloquean update y delete masivos."""

    def update(self, **kwargs):
        raise PermissionError("La tabla de auditoría es de solo inserción.")

    def delete(self):
        raise PermissionError("La tabla de auditoría es de solo inserción.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise PermissionError("La tabla de auditoría es de solo inserción.")


class Auditoria(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="id_auditoria")
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_column="id_usuario",
        related_name="eventos_auditoria",
        help_text="Quien hizo la acción. Vacío en intentos con un correo inexistente.",
    )
    accion = models.CharField(max_length=40, db_index=True)
    entidad = models.CharField(max_length=60)
    entidad_id = models.CharField(max_length=64, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    objects = AuditoriaQuerySet.as_manager()

    class Meta:
        db_table = "auditoria"
        ordering = ["-fecha", "-id"]
        verbose_name = "evento de auditoría"
        verbose_name_plural = "auditoría"
        indexes = [models.Index(fields=["entidad", "entidad_id"])]

    def __str__(self) -> str:
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.accion} {self.entidad}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Los registros de auditoría no se pueden modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Los registros de auditoría no se pueden eliminar.")
