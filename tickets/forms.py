import json

from django import forms

from core.forms import EstiloFormMixin
from core.permisos import TRABAJADOR, codigo_perfil
from cuentas.models import Usuario
from inventario.models import Equipo
from inventario.selectors import equipos_visibles
from tickets.models import Ticket
from tickets.services import tecnicos_elegibles


class FormularioTicket(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["tipo", "equipo", "descripcion"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 5, "maxlength": 1500, "placeholder": "¿Qué pasó? ¿Dónde? ¿Desde cuándo?"})}
        labels = {"equipo": "Equipo (si lo conoces)", "descripcion": "Descripción de la falla"}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipo"].required = False
        self.fields["equipo"].queryset = equipos_visibles(usuario).exclude(estado=Equipo.BAJA) if usuario else Equipo.objects.none()
        if usuario is not None and codigo_perfil(usuario) == TRABAJADOR:
            del self.fields["tipo"]  # el trabajador solo reporta fallas


class FormularioAprobar(EstiloFormMixin, forms.Form):
    tecnico = forms.ModelChoiceField(queryset=Usuario.objects.none(), label="Asignar a")

    def __init__(self, *args, ticket=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnico"].queryset = tecnicos_elegibles(ticket)
        self.fields["tecnico"].label_from_instance = lambda u: f"{u} · {u.perfil.nombre}" + (f" ({u.empresa_externa})" if u.empresa_externa else "")


class FormularioMotivo(EstiloFormMixin, forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=300, widget=forms.Textarea(attrs={"rows": 3, "maxlength": 300}))


class FormularioRealizar(EstiloFormMixin, forms.Form):
    observacion = forms.CharField(label="Observaciones del trabajo", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    materiales_json = forms.CharField(required=False, widget=forms.HiddenInput)
    documentos_json = forms.CharField(required=False, widget=forms.HiddenInput)

    def _json(self, nombre):
        crudo = self.cleaned_data.get(nombre) or "[]"
        try:
            return json.loads(crudo)
        except ValueError as exc:
            raise forms.ValidationError("Datos inválidos; recarga la página e inténtalo de nuevo.") from exc

    def clean_materiales_json(self):
        return self._json("materiales_json")

    def clean_documentos_json(self):
        return self._json("documentos_json")
