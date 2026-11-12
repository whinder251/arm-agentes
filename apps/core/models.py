from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Proveedor(models.Model):
    """Servicio externo de IA al que se le pide trabajo."""

    nombre = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=300)
    # Se guarda en claro en esta etapa; ver pendiente de cifrado en docs/plan.md.
    api_key = models.TextField(blank=True)
    rpm = models.PositiveIntegerField(
        default=0, help_text="Peticiones por minuto. 0 significa sin límite."
    )
    limite_diario = models.PositiveIntegerField(
        default=0, help_text="Llamadas por día. 0 significa sin límite."
    )

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ModeloLLM(models.Model):
    """Modelo concreto ofrecido por un proveedor."""

    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.CASCADE, related_name="modelos"
    )
    model_id = models.CharField(max_length=120)
    prioridad = models.PositiveSmallIntegerField(
        default=100, help_text="Menor valor se intenta antes."
    )
    json_nativo = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "modelo de LLM"
        verbose_name_plural = "modelos de LLM"
        ordering = ["prioridad", "model_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "model_id"], name="unique_modelo_por_proveedor"
            )
        ]

    def __str__(self):
        return f"{self.proveedor.nombre} / {self.model_id}"


class Habilidad(models.Model):
    """Capacidad concreta que sabe ejecutar un agente."""

    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    plantilla_prompt = models.TextField()
    esquema_salida = models.JSONField(default=dict)

    class Meta:
        verbose_name = "habilidad"
        verbose_name_plural = "habilidades"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Agente(models.Model):
    """Quién ejecuta el trabajo y con qué habilidades."""

    nombre = models.CharField(max_length=100, unique=True)
    rol = models.TextField(help_text="System prompt del agente.")
    temperatura = models.FloatField(
        default=0.7, validators=[MinValueValidator(0.0), MaxValueValidator(2.0)]
    )
    modelo = models.ForeignKey(
        ModeloLLM,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agentes",
    )
    habilidades = models.ManyToManyField(
        Habilidad, blank=True, related_name="agentes"
    )

    class Meta:
        verbose_name = "agente"
        verbose_name_plural = "agentes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
