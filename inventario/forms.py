from django import forms
from django.utils import timezone

from core.forms import EstiloFormMixin
from core.permisos import TECNICO_EXTERNO
from cuentas.models import Usuario
from inventario.models import Equipo, Sucursal, VersionSoftware


class FormularioEquipo(EstiloFormMixin, forms.ModelForm):
    tecnicos_externos = forms.ModelMultipleChoiceField(
        queryset=Usuario.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Técnicos externos asignados",
    )

    class Meta:
        model = Equipo
        fields = ["codigo", "nombre", "categoria", "sucursal", "marca", "modelo", "ubicacion", "estado", "tecnicos_externos"]
        widgets = {"estado": forms.Select()}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnicos_externos"].queryset = Usuario.objects.filter(
            perfil__codigo=TECNICO_EXTERNO, is_active=True
        ).order_by("empresa_externa", "apellido")
        self.fields["codigo"].required = False
        if usuario is not None and usuario.sucursal_id:
            self.fields["sucursal"].queryset = Sucursal.objects.filter(pk=usuario.sucursal_id)
            self.fields["sucursal"].initial = usuario.sucursal_id
        # La baja se hace con su propia acción, que conserva el historial.
        self.fields["estado"].choices = [c for c in Equipo.ESTADOS if c[0] != Equipo.BAJA]


class FormularioVersion(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = VersionSoftware
        fields = ["tipo", "version", "fecha", "actual"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].initial = timezone.localdate()
