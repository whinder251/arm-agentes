from django import forms

from apps.core.models import Agente, Credencial, FormatoSalida, Habilidad, Herramienta, Proveedor, ModeloLLM, DestinoPublicacion


class ProveedorForm(forms.ModelForm):
    cambiar_api_key = forms.BooleanField(required=False, label='Cambiar API key')

    class Meta:
        model = Proveedor
        fields = ["nombre", "base_url", "api_key", "rpm", "limite_diario"]
        widgets = {
            "api_key": forms.TextInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.api_key:
            self.initial['api_key'] = f"****{self.instance.api_key[-4:]}"
            self.fields['api_key'].widget.attrs.update({'readonly': 'readonly'})


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
        fields = ["nombre", "slug", "modo_ejecucion", "instrucciones"]
        widgets = {
            "instrucciones": forms.Textarea(attrs={"rows": 6}),
        }


class FormatoSalidaForm(forms.ModelForm):
    class Meta:
        model = FormatoSalida
        fields = ["nombre", "slug", "descripcion", "esquema", "version", "permite_parcial", "plantilla_formato", "es_sistema"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "esquema": forms.Textarea(attrs={"rows": 6}),
            "plantilla_formato": forms.Textarea(attrs={"rows": 6}),
        }


class HerramientaForm(forms.ModelForm):
    class Meta:
        model = Herramienta
        fields = ["nombre", "slug", "tipo", "descripcion", "configuracion", "credencial", "es_sistema"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "configuracion": forms.Textarea(attrs={"rows": 6}),
            "credencial": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name != "credencial":
                field.widget.attrs.update({'class': 'input'})
        if "credencial" in self.fields:
            self.fields["credencial"].queryset = Credencial.objects.all().order_by("nombre")
            self.fields["credencial"].empty_label = "— Sin credencial —"
            self.fields["credencial"].help_text = (
                "Selecciona una credencial centralizada. "
                "La configuración JSON a continuación solo debe contener parámetros de comportamiento "
                "(endpoints, params), nunca secretos."
            )


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


class CredencialForm(forms.ModelForm):
    class Meta:
        model = Credencial
        fields = ["nombre", "slug", "tipo", "secreto_cifrado", "metadata", "es_sistema"]
        labels = {
            "secreto_cifrado": "API Key",
        }
        help_texts = {
            "secreto_cifrado": "Clave secreta que se usará para autenticar las peticiones. Puedes referenciarla en el Metadata usando {{secreto}}.",
        }
        widgets = {
            "secreto_cifrado": forms.PasswordInput(attrs={"placeholder": "sk-... o {{secreto}}"}),
            "metadata": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.secreto_cifrado:
            self.initial['secreto_cifrado'] = f"****{self.instance.secreto_cifrado[-4:]}"
            self.fields['secreto_cifrado'].widget.attrs.update({'readonly': 'readonly'})


class DestinoPublicacionForm(forms.ModelForm):
    """Formulario para crear/editar un destino de publicación."""

    cambiar_credenciales = forms.BooleanField(
        required=False, label='Cambiar credenciales'
    )

    class Meta:
        model = DestinoPublicacion
        fields = ["nombre", "tipo", "url", "usuario", "credenciales", "activa"]
        widgets = {
            "credenciales": forms.PasswordInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.credenciales:
            self.initial['credenciales'] = f"****{self.instance.credenciales[-4:]}"
            self.fields['credenciales'].widget.attrs.update({'readonly': 'readonly'})
