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


class ContadorCuota(models.Model):
    """Llamadas reservadas a un proveedor en una fecha local concreta."""

    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.CASCADE, related_name="contadores_cuota"
    )
    fecha = models.DateField()
    usadas = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "contador de cuota"
        verbose_name_plural = "contadores de cuota"
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "fecha"],
                name="unique_cuota_por_proveedor_y_fecha",
            )
        ]

    def __str__(self):
        return f"{self.proveedor.nombre} {self.fecha}: {self.usadas}"


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


class Tarea(models.Model):
    """Unidad de trabajo que pasa por estados hasta completarse."""

    class Estado(models.TextChoices):
        COLA = "cola", "En cola"
        CURSO = "curso", "En curso"
        REVISION = "revision", "En revisión"
        OK = "ok", "Completada"
        FALLO = "fallo", "Fallida"

    TRANSICIONES = {
        Estado.COLA: {Estado.CURSO, Estado.FALLO},
        Estado.CURSO: {Estado.COLA, Estado.REVISION, Estado.FALLO},
        Estado.REVISION: {Estado.OK, Estado.FALLO},
        Estado.OK: set(),
        Estado.FALLO: set(),
    }

    estado = models.CharField(
        max_length=10, choices=Estado.choices, default=Estado.COLA
    )
    agente = models.ForeignKey(
        Agente,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tareas",
    )
    habilidad = models.ForeignKey(
        Habilidad, on_delete=models.PROTECT, related_name="tareas"
    )
    payload = models.JSONField(default=dict, blank=True)
    depende_de = models.ManyToManyField(
        "self", blank=True, symmetrical=False, related_name="dependientes"
    )
    intentos = models.PositiveSmallIntegerField(default=0)
    actualizado_en = models.DateTimeField(
        auto_now=True, help_text="Último latido del worker que ejecuta la tarea."
    )

    class Meta:
        verbose_name = "tarea"
        verbose_name_plural = "tareas"

    def __str__(self):
        return f"Tarea {self.pk} ({self.get_estado_display()})"

    def transicionar(self, nuevo_estado):
        """Aplica una transición válida o lanza ValueError."""
        if nuevo_estado not in self.TRANSICIONES.get(self.estado, set()):
            raise ValueError(
                f"Transición no permitida: {self.estado} -> {nuevo_estado}"
            )
        self.estado = nuevo_estado
        self.save(update_fields=["estado"])


class Ejecucion(models.Model):
    """Registro de una llamada a un modelo dentro de una tarea."""

    tarea = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, related_name="ejecuciones"
    )
    modelo_usado = models.CharField(max_length=120, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    ms = models.PositiveIntegerField(default=0)
    salida = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "ejecución"
        verbose_name_plural = "ejecuciones"

    def __str__(self):
        return f"Ejecución {self.pk} de la tarea {self.tarea_id}"


class Artefacto(models.Model):
    """Resultado versionado producido por una tarea."""

    tarea = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, related_name="artefactos"
    )
    version = models.PositiveIntegerField(default=1)
    contenido = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "artefacto"
        verbose_name_plural = "artefactos"
        ordering = ["tarea", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["tarea", "version"], name="unique_version_por_tarea"
            )
        ]

    def __str__(self):
        return f"Artefacto v{self.version} de la tarea {self.tarea_id}"
