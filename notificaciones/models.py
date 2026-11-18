from django.conf import settings
from django.db import models
from django.utils import timezone


class Notificacion(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_notificacion")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_column="id_usuario", related_name="notificaciones"
    )
    texto = models.CharField(max_length=200)
    url = models.CharField(max_length=200, blank=True)
    clave = models.CharField(max_length=80, blank=True, help_text="Evita avisar dos veces lo mismo.")
    fecha = models.DateTimeField(default=timezone.now)
    leida = models.BooleanField(default=False)

    class Meta:
        db_table = "notificacion"
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["usuario", "leida", "-fecha"])]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "clave"], condition=~models.Q(clave=""), name="notificacion_clave_unica_por_usuario"
            )
        ]

    def __str__(self) -> str:
        return self.texto

    def marcar_leida(self) -> None:
        if not self.leida:
            self.leida = True
            self.save(update_fields=["leida"])
