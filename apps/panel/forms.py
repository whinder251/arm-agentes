from django import forms

from apps.core.models import Proveedor, ModeloLLM


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "base_url", "api_key", "rpm", "limite_diario"]


class ModeloLLMForm(forms.ModelForm):
    class Meta:
        model = ModeloLLM
        fields = ["proveedor", "model_id", "prioridad", "json_nativo", "activo"]
