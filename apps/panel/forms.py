from django import forms

from apps.core.models import Agente, Habilidad, Proveedor, ModeloLLM


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "base_url", "api_key", "rpm", "limite_diario"]


class ModeloLLMForm(forms.ModelForm):
    class Meta:
        model = ModeloLLM
        fields = ["proveedor", "model_id", "prioridad", "json_nativo", "activo"]


class HabilidadForm(forms.ModelForm):
    modo_ejecucion = forms.ChoiceField(
        choices=[("auto", "Automático"), ("manual", "Requiere aprobación")],
        required=False,
        initial="auto",
        widget=forms.Select,
    )

    class Meta:
        model = Habilidad
        fields = ["nombre", "slug", "modo_ejecucion", "plantilla_prompt", "esquema_salida"]
        widgets = {
            "plantilla_prompt": forms.Textarea(attrs={"rows": 6}),
            "esquema_salida": forms.Textarea(attrs={"rows": 4}),
        }


class AgenteForm(forms.ModelForm):
    """Datos del agente; las habilidades se eligen en el template."""

    class Meta:
        model = Agente
        fields = ["nombre", "rol", "temperatura", "modelo"]
        widgets = {
            "rol": forms.Textarea(attrs={"rows": 14}),
            "temperatura": forms.NumberInput(
                attrs={"type": "range", "min": 0, "max": 2, "step": 0.1}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modelo"].empty_label = None
        self.fields["modelo"].required = False
        self.fields["modelo"].widget = forms.RadioSelect(
            choices=self.fields["modelo"].choices
        )
