from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from inventario.models import Equipo
from tickets import estados


class Ticket(models.Model):
    FALLA = "falla"
    CORRECTIVA = "correctiva"
    SOLICITUD = "solicitud"
    TIPOS = [(FALLA, "Reporte de falla"), (CORRECTIVA, "Mantención correctiva"), (SOLICITUD, "Solicitud")]
    ESTADOS = [(e, e) for e in estados.ESTADOS]

    id = models.AutoField(primary_key=True, db_column="id_ticket")
    tipo = models.CharField(max_length=15, choices=TIPOS, default=FALLA)
    descripcion = models.TextField(max_length=1500)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=estados.PENDIENTE, db_index=True)
    equipo = models.ForeignKey(
        Equipo, null=True, blank=True, on_delete=models.PROTECT, db_column="id_equipo", related_name="tickets"
    )
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="id_solicitante", related_name="tickets_solicitados"
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_column="id_tecnico",
        related_name="tickets_asignados",
    )
    fecha_creacion = models.DateTimeField(default=timezone.now)
    inicio_trabajo = models.DateTimeField(null=True, blank=True)
    termino_trabajo = models.DateTimeField(null=True, blank=True)
    motivo_rechazo = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "ticket"
        ordering = ["-fecha_creacion"]
        indexes = [models.Index(fields=["estado", "-fecha_creacion"]), models.Index(fields=["tecnico", "estado"])]

    def __str__(self) -> str:
        return f"{self.numero} · {self.get_tipo_display()}"

    @property
    def numero(self) -> str:
        return f"T-{self.pk:05d}" if self.pk else "T-nuevo"

    @property
    def esta_abierto(self) -> bool:
        return self.estado not in estados.ESTADOS_FINALES


class HistorialEstado(models.Model):
    """Cada cambio de estado queda registrado (composición: no existe sin su ticket)."""

    id = models.AutoField(primary_key=True, db_column="id_historial")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, db_column="id_ticket", related_name="historial")
    estado = models.CharField(max_length=20)
    fecha = models.DateTimeField(default=timezone.now)
    observacion = models.CharField(max_length=300, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, db_column="id_usuario", related_name="+"
    )

    class Meta:
        db_table = "historial_estado"
        ordering = ["fecha", "id"]


class Material(models.Model):
    id = models.AutoField(primary_key=True, db_column="id_material")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, db_column="id_ticket", related_name="materiales")
    descripcion = models.CharField(max_length=120)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unidad = models.CharField(max_length=20, default="unidad")

    class Meta:
        db_table = "material"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.cantidad} {self.unidad} de {self.descripcion}"


class DocumentoRespaldo(models.Model):
    """Factura o guía de despacho. Solo guarda la URL de la foto en Cloudinary."""

    FACTURA = "factura"
    GUIA = "guia_despacho"
    OTRO = "otro"
    TIPOS = [(FACTURA, "Factura"), (GUIA, "Guía de despacho"), (OTRO, "Otro")]

    id = models.AutoField(primary_key=True, db_column="id_documento_respaldo")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, db_column="id_ticket", related_name="documentos")
    tipo = models.CharField(max_length=15, choices=TIPOS, default=FACTURA)
    numero = models.CharField(max_length=30, blank=True)
    proveedor = models.CharField(max_length=100, blank=True)
    monto = models.PositiveIntegerField(null=True, blank=True, help_text="Pesos chilenos, sin decimales.")
    url_foto = models.CharField(max_length=255)

    class Meta:
        db_table = "documento_respaldo"
        ordering = ["id"]
