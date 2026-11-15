from django import forms


class EstiloFormMixin:
    """Agrega las clases CSS de la guía de estilo COVEPA a todos los campos."""

    def _aplicar_estilo(self):
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "casilla")
            elif isinstance(widget, forms.RadioSelect):
                continue
            else:
                widget.attrs.setdefault("class", "campo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aplicar_estilo()
