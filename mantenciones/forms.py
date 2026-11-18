import json

from django import forms

from core.forms import EstiloFormMixin
from core.validators import ErrorValidacion, validar_definicion_campos
from inventario.models import Equipo
from inventario.selectors import equipos_visibles
from mantenciones.models import PlanMantencion, Plantilla


class FormularioPlantilla(EstiloFormMixin, forms.ModelForm):
    campos_json = forms.CharField(widget=forms.HiddenInput, label="Campos")

    class Meta:
        model = Plantilla
        fields = ["nombre", "categoria", "activa"]

    def clean_campos_json(self):
        try:
            crudo = json.loads(self.cleaned_data["campos_json"] or "[]")
        except ValueError as exc:
            raise forms.ValidationError("Los campos no tienen un formato válido.") from exc
        try:
            return validar_definicion_campos(crudo)
        except ErrorValidacion as exc:
            raise forms.ValidationError(exc.errores) from exc


class FormularioPlan(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = PlanMantencion
        fields = ["equipo", "plantilla", "actividad", "frecuencia_dias", "duracion_min", "activo"]
        labels = {"frecuencia_dias": "Frecuencia (días)", "duracion_min": "Duración estimada (min)"}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipo"].queryset = equipos_visibles(usuario).exclude(estado=Equipo.BAJA) if usuario else Equipo.objects.none()
        self.fields["plantilla"].queryset = Plantilla.objects.filter(activa=True, version_actual__gt=0)
        self.fields["plantilla"].label_from_instance = lambda p: f"{p.categoria} · {p.nombre}"
