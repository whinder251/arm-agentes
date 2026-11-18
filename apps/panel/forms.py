from django import forms

from apps.core.models import Agente, Credencial, FormatoSalida, Habilidad, Herramienta, Proveedor, ModeloLLM, DestinoPublicacion, InvestigacionProgramada


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre", "base_url", "api_key", "rpm", "limite_diario"]
        widgets = {
            "api_key": forms.PasswordInput(attrs={"placeholder": "sk-... o {{secreto}}"}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.api_key:
            self.initial['api_key'] = f"****{self.instance.api_key[-4:]}"
            self.fields['api_key'].required = False
            self.fields['api_key'].widget.attrs.pop('readonly', None)

    def clean(self):
        cleaned_data = super().clean()
        is_edit = self.instance and self.instance.pk
        secreto = cleaned_data.get('api_key')

        if is_edit and (not secreto or (isinstance(secreto, str) and secreto.startswith('****'))):
            # No se escribió nada o se dejó el placeholder enmascarado: conservar original
            cleaned_data['api_key'] = self.instance.api_key
        return cleaned_data


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
        # configuracion no es requerida en el form porque se construye desde campos estructurados
        # o se proporciona en modo avanzado
        self.fields["configuracion"].required = False
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
            "secreto_cifrado": "Clave secreta que se usará para autenticar las peticiones. Puedes referenciarla en el Metadata usando {{secreto}}. Déjalo vacío para conservar la clave actual.",
        }
        widgets = {
            "secreto_cifrado": forms.PasswordInput(attrs={"placeholder": "sk-... o {{secreto}}"}, render_value=True),
            "metadata": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.secreto_cifrado:
            self.initial['secreto_cifrado'] = f"****{self.instance.secreto_cifrado[-4:]}"
            self.fields['secreto_cifrado'].required = False
            self.fields['secreto_cifrado'].widget.attrs.pop('readonly', None)

    def clean(self):
        cleaned_data = super().clean()
        is_edit = self.instance and self.instance.pk
        secreto = cleaned_data.get('secreto_cifrado')

        if is_edit and (not secreto or (isinstance(secreto, str) and secreto.startswith('****'))):
            # No se escribió nada o se dejó el placeholder enmascarado: conservar original
            cleaned_data['secreto_cifrado'] = self.instance.secreto_cifrado
        return cleaned_data


class DestinoPublicacionForm(forms.ModelForm):
    """Formulario para crear/editar un destino de publicación."""

    class Meta:
        model = DestinoPublicacion
        fields = ["nombre", "tipo", "url", "usuario", "credenciales", "activa"]
        widgets = {
            "credenciales": forms.PasswordInput(attrs={"placeholder": "sk-... o {{secreto}}"}, render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'input'})
        if self.instance and self.instance.pk and self.instance.credenciales:
            self.initial['credenciales'] = f"****{self.instance.credenciales[-4:]}"
            self.fields['credenciales'].required = False
            self.fields['credenciales'].widget.attrs.pop('readonly', None)

    def clean(self):
        cleaned_data = super().clean()
        is_edit = self.instance and self.instance.pk
        secreto = cleaned_data.get('credenciales')

        if is_edit and (not secreto or (isinstance(secreto, str) and secreto.startswith('****'))):
            # No se escribió nada o se dejó el placeholder enmascarado: conservar original
            cleaned_data['credenciales'] = self.instance.credenciales
        return cleaned_data


class InvestigacionForm(forms.ModelForm):
    """Formulario simplificado para crear una investigación programada.

    La frecuencia se renderiza manualmente como .segmented en el template,
    no usando el widget Select por defecto.
    """

    class Meta:
        model = InvestigacionProgramada
        fields = ["nombre", "urls_objetivo", "frecuencia"]
        widgets = {
            "urls_objetivo": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nombre"].widget.attrs.update({"class": "input"})
        self.fields["urls_objetivo"].widget.attrs.update({"class": "textarea"})
        self.fields["frecuencia"].widget = forms.RadioSelect()
        self.fields["frecuencia"].widget.attrs.update({"class": "segmented-radio"})
