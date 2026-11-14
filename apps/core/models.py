import os

from cryptography.fernet import Fernet, InvalidToken
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# Clave de cifrado para api_key de Proveedor (RB-013).
# Es obligatorio definir ARM_ENCRYPTION_KEY como variable de entorno.
from django.core.exceptions import ImproperlyConfigured
_ENC_KEY = os.environ.get("ARM_ENCRYPTION_KEY")
if not _ENC_KEY:
    raise ImproperlyConfigured("La variable de entorno ARM_ENCRYPTION_KEY es obligatoria para cifrar las API keys.")
_fernet = Fernet(_ENC_KEY.encode())
class EncryptedTextField(models.TextField):
    """Campo de texto que cifra al guardar y descifra al leer desde la BD.

    La columna en BD sigue siendo TextField; la transformación es en Python.
    Valores legacy en texto plano (antes del cifrado) se devuelven tal cual
    cuando falla el descifrado (InvalidToken), para no romper proveedores
    creados antes de este paso.
    """

    def get_prep_value(self, value):
        if value is None:
            return None
        return _fernet.encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        try:
            return _fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return value


class Proveedor(models.Model):
    """Servicio externo de IA al que se le pide trabajo."""

    nombre = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(max_length=300)
    # api_key se cifra antes de guardar (RB-013). La columna BD sigue siendo
    # TextField; la transformación es en Python vía EncryptedTextField.
    api_key = EncryptedTextField(blank=True)
    rpm = models.PositiveIntegerField(
        default=0, help_text="Peticiones por minuto. 0 significa sin límite."
    )
    limite_diario = models.PositiveIntegerField(
        default=0, help_text="Llamadas por día. 0 significa sin límite."
    )
    limite_tokens_diario = models.IntegerField(
        default=0, help_text="Tokens por día. 0 = sin límite."
    )
    tokens_consumidos_hoy = models.IntegerField(
        default=0, help_text="Tokens consumidos hoy. Se resetea cada día."
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
    modo_ejecucion = models.CharField(
        max_length=10,
        choices=[("auto", "Automático"), ("manual", "Requiere aprobación")],
        default="auto",
    )

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
    paso_workflow = models.ForeignKey(
        "PasoWorkflow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tareas",
        help_text="Paso del workflow al que pertenece esta tarea.",
    )
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


class Equipo(models.Model):
    """Grupo de agentes que pueden ejecutar un workflow."""

    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    agentes = models.ManyToManyField(
        Agente, related_name="equipos", blank=True
    )

    class Meta:
        verbose_name = "equipo"
        verbose_name_plural = "equipos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Workflow(models.Model):
    """Flujo de trabajo multi-paso que encadena habilidades y agentes."""

    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    estado = models.CharField(
        max_length=20,
        choices=[
            ("borrador", "Borrador"),
            ("en_ejecucion", "En ejecución"),
            ("completado", "Completado"),
            ("fallido", "Fallido"),
        ],
        default="borrador",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    equipo = models.ForeignKey(
        Equipo,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workflows",
        help_text="Equipo de agentes asignado al workflow.",
    )

    class Meta:
        verbose_name = "workflow"
        verbose_name_plural = "workflows"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class PasoWorkflow(models.Model):
    """Paso de un workflow: qué habilidad ejecuta y con qué agente."""

    workflow = models.ForeignKey(
        Workflow, on_delete=models.CASCADE, related_name="pasos"
    )
    orden = models.PositiveIntegerField(help_text="Orden de ejecución")
    habilidad = models.ForeignKey(
        Habilidad, on_delete=models.PROTECT, related_name="pasos_workflow"
    )
    agente = models.ForeignKey(
        Agente,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pasos_workflow",
        help_text="Si es nulo, el orquestador asignará uno con esta habilidad",
    )
    modo_ejecucion = models.CharField(
        max_length=10,
        choices=[("auto", "Automático"), ("manual", "Requiere aprobación")],
        default="auto",
    )

    class Meta:
        verbose_name = "paso de workflow"
        verbose_name_plural = "pasos de workflow"
        ordering = ["orden"]

    def __str__(self):
        return f"Paso {self.orden} de {self.workflow.nombre}"
