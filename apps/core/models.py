import os
import hashlib
import secrets
import ipaddress
import socket
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models, transaction


# Clave de cifrado para api_key de Proveedor (RB-013).
# Es obligatorio definir ARM_ENCRYPTION_KEY como variable de entorno.
from django.core.exceptions import ImproperlyConfigured, ValidationError
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
    tipo_adaptador = models.CharField(
        max_length=20,
        choices=[
            ("gemini", "Gemini"),
            ("openrouter", "OpenRouter"),
            ("custom", "Personalizado"),
        ],
        default="custom",
        help_text="Adaptador interno que ejecuta las llamadas a este proveedor.",
    )
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
    capacidades = models.JSONField(default=list)
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


class FormatoSalida(models.Model):
    """Estructura de salida esperada, desacoplada de la habilidad de comportamiento.

    Permite que un usuario no técnico seleccione, por separado:
    - el comportamiento/tono (Habilidad.instrucciones) y
    - el formato de salida (FormatoSalida.esquema).
    """

    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    esquema = models.JSONField(default=dict)
    version = models.CharField(max_length=20, default="v1")
    permite_parcial = models.BooleanField(default=False)
    plantilla_formato = models.TextField(
        blank=True,
        help_text="Plantilla de ejemplo JSON que se inyecta en el prompt del modelo.",
    )
    es_sistema = models.BooleanField(
        default=False,
        help_text="Recurso predefinido por el sistema, protegido de edición/eliminación.",
    )

    class Meta:
        verbose_name = "formato de salida"
        verbose_name_plural = "formatos de salida"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Credencial(models.Model):
    """Almacén centralizado de secretos (estilo n8n). Cifrado reversible para uso en runtime."""

    class Tipo(models.TextChoices):
        API_KEY = "api_key", "API Key"
        BASIC = "basic", "Basic Auth (usuario:contraseña)"
        BEARER = "bearer", "Bearer Token"
        JSON = "json", "JSON Credenciales (Google, etc.)"

    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    secreto_cifrado = EncryptedTextField(
        help_text="Secretos cifrados de forma reversible. Usar la misma importación que DestinoPublicacion."
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Datos no sensibles como base_url, endpoint, username, etc."
    )
    es_sistema = models.BooleanField(
        default=False,
        help_text="Recurso predefinido por el sistema, protegido de edición/eliminación."
    )

    class Meta:
        verbose_name = "credencial"
        verbose_name_plural = "credenciales"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Herramienta(models.Model):
    """Acción externa que puede invocar un agente (scraping, búsqueda, DB, API, Python)."""

    class Tipo(models.TextChoices):
        SCRAPING = "scraping", "Scraping web"
        BUSQUEDA = "busqueda", "Búsqueda web"
        BASE_DATOS = "database", "Consulta a base de datos"
        API_EXTERNA = "api", "API externa"
        PYTHON = "python", "Código Python sandbox"

    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField(blank=True)
    configuracion = models.JSONField(
        default=dict,
        help_text="Parámetros específicos del tipo (selector, endpoint, query, etc.). No incluir secretos aquí.",
    )
    credencial = models.ForeignKey(
        Credencial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="herramientas",
        help_text="Credencial centralizada para esta herramienta."
    )
    es_sistema = models.BooleanField(
        default=False,
        help_text="Recurso predefinido por el sistema, protegido de edición/eliminación.",
    )

    class Meta:
        verbose_name = "herramienta"
        verbose_name_plural = "herramientas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Habilidad(models.Model):
    """Capacidad concreta de comportamiento/tono/estilo que sabe ejecutar un agente."""

    nombre = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    instrucciones = models.TextField()
    modo_ejecucion = models.CharField(
        max_length=10,
        choices=[("auto", "Automático"), ("manual", "Requiere aprobación")],
        default="auto",
    )
    es_sistema = models.BooleanField(
        default=False,
        help_text="Recurso predefinido por el sistema, protegido de edición/eliminación.",
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
    formato_salida = models.ForeignKey(
        FormatoSalida,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="agentes",
        help_text="Formato de salida por defecto para este agente.",
    )
    herramientas = models.ManyToManyField(
        Herramienta,
        blank=True,
        related_name="agentes",
        help_text="Herramientas externas disponibles para este agente.",
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
        ERROR = "error", "Error"
        FALLO = "fallo", "Fallida"

    TRANSICIONES = {
        Estado.COLA: {Estado.CURSO, Estado.FALLO},
        Estado.CURSO: {Estado.COLA, Estado.REVISION, Estado.FALLO, Estado.ERROR, Estado.OK},
        Estado.REVISION: {Estado.OK, Estado.FALLO},
        Estado.OK: {Estado.REVISION},
        Estado.ERROR: set(),
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
    formato_salida = models.ForeignKey(
        FormatoSalida,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tareas",
        help_text="Formato de salida override para esta tarea (si no, se usa el del agente).",
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
        self.save(update_fields=["estado", "actualizado_en"])


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


class Artefacto(models.Model):
    """Resultado versionado producido por una tarea."""

    tarea = models.ForeignKey(
        Tarea, on_delete=models.CASCADE, related_name="artefactos"
    )
    version = models.PositiveIntegerField(default=1)
    contenido = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    raw_response = models.TextField(null=True, blank=True)

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


class IntegracionConfig(models.Model):
    """Credenciales de integraciones externas (no proveedores LLM).

    Las credenciales que solo deben verificarse (como API keys de webhook)
    se almacenan como hash SHA-256, nunca en texto plano ni cifradas de forma
    reversible (docs/estandares/seguridad.md §3).
    """

    class Tipo(models.TextChoices):
        ARM_API = "arm_api", "ARM API"
        WORDPRESS = "wordpress", "WordPress"
        SLACK = "slack", "Slack"

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    credenciales = models.TextField(
        help_text="Hash SHA-256 de la credencial (no texto plano)."
    )
    activa = models.BooleanField(default=True)
    proyecto_id = models.IntegerField(null=True, blank=True, db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuración de integración"
        verbose_name_plural = "configuraciones de integración"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"

    def clean(self):
        if self.tipo == self.Tipo.ARM_API and self.activa:
            duplicados = (
                IntegracionConfig.objects.filter(
                    tipo=self.Tipo.ARM_API, activa=True
                )
                .exclude(pk=self.pk)
            )
            if duplicados.exists():
                raise ValidationError(
                    "Ya existe una integración ARM API activa. "
                    "Solo puede haber una a la vez."
                )

    @classmethod
    def rotar_clave_arm(cls):
        """Rota la clave ARM API guardando solo su hash SHA-256.

        Genera un nuevo token seguro, lo hashea y lo persiste en el registro
        activo de tipo ``arm_api``. Retorna el token en texto plano para que
        la vista lo muestre una sola vez (nunca se guarda sin cifrar en BD).
        """
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        with transaction.atomic():
            registro = (
                cls.objects.filter(tipo=cls.Tipo.ARM_API, activa=True)
                .select_for_update()
                .first()
            )
            if registro is None:
                registro = cls(
                    nombre="ARM API",
                    tipo=cls.Tipo.ARM_API,
                    credenciales=token_hash,
                    activa=True,
                )
            else:
                registro.credenciales = token_hash
            registro.save(update_fields=["credenciales", "actualizado_en"])

        return token


def validar_url_segura(value):
    """Valida que la URL use esquema seguro y no apunte a redes internas (SSRF).

    Rechaza esquemas distintos de http/https y direcciones loopback, privadas,
    link-local, multicast, reservadas y endpoints de metadatos de nube.
    """
    URLValidator()(value)
    try:
        partes = urlparse(value)
    except ValueError:
        raise ValidationError("URL no válida.")
    esquema = (partes.scheme or "").lower()
    if esquema not in {"http", "https"}:
        raise ValidationError(
            f"Esquema no permitido: {esquema or '(vacío)'}. Solo se permiten http y https."
        )
    host = partes.hostname
    if not host:
        raise ValidationError("La URL debe incluir un host válido.")
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        infos = []
    for familia, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        try:
            direccion = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if (
            direccion.is_loopback
            or direccion.is_private
            or direccion.is_link_local
            or direccion.is_multicast
            or direccion.is_reserved
        ):
            raise ValidationError(
                f"La URL apunta a una dirección restringida ({ip}). No se permiten "
                "direcciones privadas, loopback ni metadatos de nube."
            )
        if str(direccion) == "169.254.169.254":
            raise ValidationError(
                "La URL apunta a un endpoint de metadatos de nube, no permitido."
            )


class DestinoPublicacion(models.Model):
    """Destino de publicación (WordPress u otra API), desacoplado de proveedores LLM.

    Permite que un agente use cualquier modelo LLM y publique en cualquier
    destino configurado de forma independiente.
    """

    class Tipo(models.TextChoices):
        WORDPRESS = "wordpress", "WordPress"
        CUSTOM_API = "custom_api", "API personalizada"

    nombre = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=30, choices=Tipo.choices, default=Tipo.WORDPRESS)
    url = models.URLField(
        max_length=300,
        validators=[validar_url_segura],
        help_text="URL del destino de publicación (http o https).",
    )
    usuario = models.CharField(max_length=100, blank=True)
    credenciales = EncryptedTextField(
        blank=True,
        help_text="Contraseña o token de aplicación. Se cifra antes de guardar (RB-013).",
    )
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Ejecuta full_clean al guardar para que la validación SSRF y de
        campos se aplique siempre, se cree desde código, API o panel."""
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "destino de publicación"
        verbose_name_plural = "destinos de publicación"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class CacheRespuesta(models.Model):
    """Entrada de caché de respuestas de IA con caducidad (TTL).

    Almacena respuestas por clave de huella, con fecha de caducidad para
    permitir limpieza automática y gestión desde el admin.
    """

    clave = models.CharField(max_length=255, unique=True, db_index=True)
    modelo = models.CharField(max_length=100)
    texto = models.TextField()
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    crudo = models.JSONField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField(
        db_index=True,
        help_text="Fecha y hora de caducidad de la caché",
    )

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return f"Cache {self.clave[:16]}... ({self.modelo})"


class InvestigacionProgramada(models.Model):
    """Monitoreo programado de fuentes de competencia (RSS o Sitemap).

    Permite al usuario programar revisiones periódicas de URLs objetivo
    sin exponer la complejidad técnica del parsing ni la descarga.
    """

    FRECUENCIAS = [
        ("diaria", "Diaria"),
        ("semanal", "Semanal"),
        ("mensual", "Mensual"),
    ]

    nombre = models.CharField(max_length=200)
    urls_objetivo = models.TextField(
        help_text="Pega una URL por línea (RSS o Sitemap)"
    )
    frecuencia = models.CharField(
        max_length=20,
        choices=FRECUENCIAS,
        default="semanal",
    )
    agente = models.ForeignKey(
        "Agente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="investigaciones_asignadas",
        help_text="Agente encargado del análisis. Si está vacío, se usa el analista por defecto.",
    )
    palabras_clave = models.TextField(
        blank=True,
        default="",
        help_text="Términos específicos para enfocar o filtrar el análisis, separados por comas.",
    )
    activa = models.BooleanField(default=True)
    ultima_ejecucion = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "investigación programada"
        verbose_name_plural = "investigaciones programadas"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.nombre


class Hallazgo(models.Model):
    """Artículo o entrada detectada durante una investigación programada.

    Representa un hallazgo proveniente de un feed RSS o de un sitemap,
    vinculado a la investigación que lo descubrió.
    """

    class TipoFuente(models.TextChoices):
        RSS = "rss", "RSS"
        SITEMAP = "sitemap", "Sitemap"

    investigacion = models.ForeignKey(
        InvestigacionProgramada,
        on_delete=models.CASCADE,
        related_name="hallazgos",
        help_text="Investigación que descubrió este hallazgo.",
    )
    url_fuente = models.CharField(
        max_length=500,
        help_text="URL que se descargó para obtener este hallazgo.",
    )
    tipo_fuente = models.CharField(
        max_length=20,
        choices=TipoFuente.choices,
        help_text="Tipo de fuente: RSS o Sitemap.",
    )
    titulo = models.CharField(
        max_length=500,
        blank=True,
        help_text="Título del artículo o entrada (vacío para sitemaps).",
    )
    url_articulo = models.URLField(
        blank=True,
        help_text="URL del artículo o entrada descubierta.",
    )
    fecha_publicacion = models.CharField(
        max_length=50,
        blank=True,
        help_text="Fecha de publicación tal cual viene del feed (sin parsear).",
    )
    resumen = models.TextField(
        blank=True,
        help_text="Resumen o descripción del artículo (vacío para sitemaps).",
    )
    contenido_extraido = models.TextField(
        blank=True,
        default="",
        help_text="Texto principal del artículo extraído con trafilatura.",
    )
    detectado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "hallazgo"
        verbose_name_plural = "hallazgos"
        ordering = ["-detectado_en"]
        indexes = [
            models.Index(
                fields=["investigacion", "url_articulo"],
                name="hallazgo_inv_url_idx",
            ),
        ]

    def __str__(self):
        return self.titulo or self.url_articulo
