"""Comando de gestión idempotente para poblar datos de prueba (demo).

Siembra habilidades, agentes, equipos y workflows reutilizando proveedores y
modelos de IA existentes. No crea Proveedor ni ModeloLLM nuevos. Si no existe
ningún proveedor/modelo, aborta con mensaje claro y no crea nada parcial.

Es idempotente: al ejecutarse varias veces no duplica registros. Si un Equipo
ya existe pero no tiene agentes vinculados, se le añaden. Si un PasoWorkflow
ya existe pero tiene agente=None, se le asigna el agente correcto.
"""

import sys

from django.core.management.base import BaseCommand

from apps.core import defaults
from apps.core.models import (
    Agente,
    Equipo,
    FormatoSalida,
    Habilidad,
    Herramienta,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Workflow,
)


class Command(BaseCommand):
    help = (
        "Puebla datos de prueba (habilidades, agentes, equipos, workflows) "
        "usando proveedores y modelos existentes (idempotente)."
    )

    def _obtener_modelo(self):
        """Devuelve el primer ModeloLLM cuyo proveedor contenga 'gemini',
        o el primero disponible si no hay coincidencia."""
        modelo = (
            ModeloLLM.objects.select_related("proveedor")
            .filter(proveedor__nombre__icontains="gemini")
            .order_by("pk")
            .first()
        )
        if modelo is None:
            modelo = (
                ModeloLLM.objects.select_related("proveedor")
                .order_by("pk")
                .first()
            )
        if modelo is not None:
            capacidades = list(modelo.capacidades or [])
            for cap in ("structured_output", "json_mode"):
                if cap not in capacidades:
                    capacidades.append(cap)
            modelo.capacidades = capacidades
            modelo.save(update_fields=["capacidades"])
        return modelo

    INSTRUCCION_ROL = (
        "Debes responder estrictamente con un objeto JSON válido que cumpla "
        "el esquema de salida solicitado. No incluyas texto, explicaciones ni "
        "bloques de código markdown fuera del JSON."

    )
    def _sembrar_skills_sistema(self, modelo):
        """Sembra los recursos del sistema: FormatoSalida y Habilidad de
        Dise�o UI/UX, m�s el Agente UI/UX que los consume por defecto.

        Es idempotente: get_or_create + update de campos si ya exist�an.
        """
        esquema_componente_ui = {
            "type": "object",
            "properties": {
                "nombre_componente": {"type": "string"},
                "tag_raiz": {
                    "type": "string",
                    "enum": ["section", "article", "aside", "div"],
                },
                "clases_arm_flow": {"type": "string"},
                "estructura_html": {"type": "string"},
                "justificacion_diseno": {"type": "string"},
            },
            "required": [
                "nombre_componente",
                "tag_raiz",
                "clases_arm_flow",
                "estructura_html",
            ],
        }

        instrucciones_ui_ux = """Eres un dise�ador frontend senior experto en el sistema de dise�o 'ARM Flow'. Tu objetivo es traducir conceptos en componentes web sem�nticos, accesibles y visualmente coherentes.
REGLAS OBLIGATORIAS:
1. Cero estilos inline: Nunca uses el atributo style='...'. Usa exclusivamente las clases y variables CSS de ARM Flow.
2. Paleta intencional: M�ximo 3-4 colores con un acento definido. Prohibido gradientes p�rpura/azul gen�ricos o efectos 'glow' sin prop�sito.
3. Estructura sem�ntica: Usa <article>, <section>, <aside> en lugar de <div> gen�ricos.
4. Iconograf�a: Usa sets de iconos SVG profesionales. Nunca uses emojis como iconos de navegaci�n principal.
5. Contenedores con prop�sito: Usa 'cards' solo para agrupar informaci�n relacionada, nunca por decoraci�n.
Si suena a 'plantilla gen�rica de IA', reescribe la estructura para que sea asim�trica y con prop�sito humano."""

        formato, creado = FormatoSalida.objects.get_or_create(
            slug="componente-ui-arm",
            defaults={
                "nombre": "Componente UI Estructurado",
                "descripcion": "Estructura de salida para componentes UI del sistema de dise�o ARM Flow.",
                "esquema": esquema_componente_ui,
                "version": "v1",
                "permite_parcial": False,
                "plantilla_formato": "",
                "es_sistema": True,
            },
        )
        if not creado:
            formato.nombre = "Componente UI Estructurado"
            formato.descripcion = "Estructura de salida para componentes UI del sistema de dise�o ARM Flow."
            formato.esquema = esquema_componente_ui
            formato.version = "v1"
            formato.permite_parcial = False
            formato.es_sistema = True
            formato.save()

        habilidad, creado = Habilidad.objects.get_or_create(
            slug="experto-ui-ux-arm",
            defaults={
                "nombre": "Experto UI/UX ARM Flow",
                "instrucciones": instrucciones_ui_ux,
                "modo_ejecucion": "auto",
                "es_sistema": True,
            },
        )
        if not creado:
            habilidad.nombre = "Experto UI/UX ARM Flow"
            habilidad.instrucciones = instrucciones_ui_ux
            habilidad.modo_ejecucion = "auto"
            habilidad.es_sistema = True
            habilidad.save()

        agente, creado = Agente.objects.get_or_create(
            nombre="UI/UX",
            defaults={
                "rol": "Eres un dise�ador frontend senior experto en el sistema de dise�o 'ARM Flow'.",
                "temperatura": 0.6,
                "modelo": modelo,
                "formato_salida": formato,
            },
        )
        if not creado:
            agente.rol = (
                "Eres un dise�ador frontend senior experto en el sistema de dise�o 'ARM Flow'."
            )
            agente.temperatura = 0.6
            agente.modelo = modelo
            agente.formato_salida = formato
            agente.save()
        agente.habilidades.set([habilidad])

    def _sembrar_herramientas_sistema(self):
        """Sembrar herramientas del sistema (Plug & Play)."""
        creadas = 0
        actualizadas = 0
        for slug, datos in defaults.HERRAMIENTAS_SISTEMA.items():
            obj, created = Herramienta.objects.update_or_create(
                slug=slug,
                defaults={
                    "nombre": datos["nombre"],
                    "tipo": datos["tipo"],
                    "descripcion": datos["descripcion"],
                    "configuracion": datos["configuracion"],
                    "es_sistema": True,
                },
            )
            if created:
                creadas += 1
            else:
                actualizadas += 1
        self.stdout.write(
            f"  Herramientas: {creadas} creadas, {actualizadas} actualizadas, 0 sin cambios."
        )
        return creadas, actualizadas

    def _sembrar_habilidades_sistema(self):
        """Crea o actualiza las habilidades declaradas en defaults.py.

        Garantiza que las habilidades del sistema estén disponibles en la BD
        sin que el usuario tenga que crearlas manualmente. Es idempotente.
        """
        creadas = 0
        actualizadas = 0
        for slug, datos in defaults.HABILIDADES_SISTEMA.items():
            habilidad, created = Habilidad.objects.get_or_create(
                slug=slug,
                defaults={
                    "nombre": datos["nombre"],
                    "instrucciones": datos["instrucciones"],
                    "modo_ejecucion": datos["modo_ejecucion"],
                    "es_sistema": True,
                },
            )
            if created:
                creadas += 1
                continue
            habilidad.nombre = datos["nombre"]
            habilidad.instrucciones = datos["instrucciones"]
            habilidad.modo_ejecucion = datos["modo_ejecucion"]
            habilidad.es_sistema = True
            habilidad.save(
                update_fields=[
                    "nombre",
                    "instrucciones",
                    "modo_ejecucion",
                    "es_sistema",
                ]
            )
            actualizadas += 1
        self.stdout.write(
            f"  Habilidades del sistema: {creadas} creadas, "
            f"{actualizadas} actualizadas."
        )
        return creadas, actualizadas

    FORMATOS_SALIDA = [
        {
            "slug": "informe-investigacion",
            "nombre": "Informe de Investigación",
            "descripcion": "Estructura para resultados de investigación con hallazgos y conclusiones.",
            "esquema": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "hallazgos": {"type": "array", "items": {"type": "string"}},
                    "conclusiones": {"type": "string"},
                },
                "required": ["titulo", "hallazgos"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"titulo": "...", "hallazgos": ["..."], "conclusiones": "..."}',
        },
        {
            "slug": "articulo-seo",
            "nombre": "Artículo SEO",
            "descripcion": "Estructura para artículos de blog con título, slug, contenido y metadatos SEO.",
            "esquema": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "slug": {"type": "string"},
                    "contenido": {"type": "string"},
                    "meta_description": {"type": "string"},
                    "focus_keyword": {"type": "string"},
                },
                "required": ["titulo", "contenido"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"titulo": "...", "slug": "...", "contenido": "...", "meta_description": "...", "focus_keyword": "..."}',
        },
        {
            "slug": "revision-calidad",
            "nombre": "Revisión de Calidad",
            "descripcion": "Estructura para revisión de calidad con observaciones y estado de aprobación.",
            "esquema": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "contenido": {"type": "string"},
                    "observaciones": {"type": "array", "items": {"type": "string"}},
                    "aprobado": {"type": "boolean"},
                },
                "required": ["titulo", "contenido"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"titulo": "...", "contenido": "...", "observaciones": [], "aprobado": true}',
        },
        {
            "slug": "metadatos-seo",
            "nombre": "Metadatos SEO",
            "descripcion": "Estructura para metadatos de SEO (título, descripción, palabra clave).",
            "esquema": {
                "type": "object",
                "properties": {
                    "titulo_seo": {"type": "string"},
                    "slug": {"type": "string"},
                    "meta_descripcion": {"type": "string"},
                    "palabra_clave": {"type": "string"},
                },
                "required": ["titulo_seo", "meta_descripcion", "palabra_clave"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"titulo_seo": "...", "slug": "...", "meta_descripcion": "...", "palabra_clave": "..."}',
        },
        {
            "slug": "texto-correjido",
            "nombre": "Texto Corregido",
            "descripcion": "Estructura para texto corregido ortográficamente.",
            "esquema": {
                "type": "object",
                "properties": {
                    "contenido": {"type": "string"},
                    "cambios": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["contenido"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"contenido": "...", "cambios": []}',
        },
        {
            "slug": "titular",
            "nombre": "Titular",
            "descripcion": "Estructura para titulares atractivos.",
            "esquema": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "variantes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["titulo"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"titulo": "...", "variantes": ["..."]}',
        },
        {
            "slug": "resumen",
            "nombre": "Resumen",
            "descripcion": "Estructura para resúmenes con puntos clave.",
            "esquema": {
                "type": "object",
                "properties": {
                    "contenido": {"type": "string"},
                    "puntos_clave": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["contenido"],
            },
            "version": "v1",
            "permite_parcial": True,
            "plantilla_formato": '{"contenido": "...", "puntos_clave": ["..."]}',
        },
        {
            "slug": "traduccion",
            "nombre": "Traducción",
            "descripcion": "Estructura para textos traducidos.",
            "esquema": {
                "type": "object",
                "properties": {
                    "texto_traducido": {"type": "string"},
                    "idioma_destino": {"type": "string"},
                    "idioma_origen": {"type": "string"},
                },
                "required": ["texto_traducido", "idioma_destino"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"texto_traducido": "...", "idioma_destino": "...", "idioma_origen": "..."}',
        },
        {
            "slug": "meta-descripcion",
            "nombre": "Meta Descripción",
            "descripcion": "Estructura para meta descripción SEO.",
            "esquema": {
                "type": "object",
                "properties": {
                    "meta_descripcion": {"type": "string"},
                    "slug": {"type": "string"},
                    "palabra_clave": {"type": "string"},
                    "longitud": {"type": "integer"},
                },
                "required": ["meta_descripcion"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"meta_descripcion": "...", "slug": "...", "palabra_clave": "...", "longitud": 160}',
        },
        {
            "slug": "texto-revisado",
            "nombre": "Texto Revisado",
            "descripcion": "Estructura para texto revisado con sugerencias de estilo.",
            "esquema": {
                "type": "object",
                "properties": {
                    "contenido": {"type": "string"},
                    "sugerencias": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["contenido"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"contenido": "...", "sugerencias": []}',
        },
        {
            "slug": "texto-reescrito",
            "nombre": "Texto Reescrito",
            "descripcion": "Estructura para texto reescrito con reglas editoriales aplicadas.",
            "esquema": {
                "type": "object",
                "properties": {
                    "texto_reescrito": {"type": "string"},
                    "reglas_aplicadas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["texto_reescrito"],
            },
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": '{"texto_reescrito": "...", "reglas_aplicadas": []}',
        },
    ]

    # Mapeo de slug de habilidad -> slug de formato de salida
    HABILIDAD_FORMATO_MAP = {
        "investigar_tema": "informe-investigacion",
        "redactar_articulo": "articulo-seo",
        "reescribir_editorial": "articulo-seo",
        "revision_calidad": "revision-calidad",
        "metadatos_yoast": "metadatos-seo",
        "corregir_ortografia": "texto-correjido",
        "optimizar_seo": "articulo-seo",
        "crear_titular": "titular",
        "resumir_contenido": "resumen",
        "traducir_texto": "traduccion",
        "generar_meta_descripcion": "meta-descripcion",
        "revisar_estilo": "texto-revisado",
        "reescritura": "texto-reescrito",
    }

    # Habilidades con instrucciones (ex plantilla_prompt) y referencia al formato
    HABILIDADES = [
        {
            "slug": "investigar_tema",
            "nombre": "Investigar tema",
            "instrucciones": (
                "Investiga a fondo el tema: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "informe-investigacion",
        },
        {
            "slug": "redactar_articulo",
            "nombre": "Redactar artículo",
            "instrucciones": (
                "Redacta un artículo basado en: {{ texto }}\n\n"
                +    " Entregas siempre el resultado en el formato exacto que declare la instrucción de la tarea, sin prosa adicional."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "articulo-seo",
        },
        {
            "slug": "reescribir_editorial",
            "nombre": "Reescribir editorial",
            "instrucciones": (
                "Reescribe con tono editorial: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "articulo-seo",
        },
        {
            "slug": "revision_calidad",
            "nombre": "Revisión de calidad",
            "instrucciones": (
                "Revisa la calidad de: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "manual",
            "formato_slug": "revision-calidad",
        },
        {
            "slug": "metadatos_yoast",
            "nombre": "Metadatos Yoast",
            "instrucciones": (
                "Genera metadatos SEO para: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "metadatos-seo",
        },
        {
            "slug": "corregir_ortografia",
            "nombre": "Corregir ortografía",
            "instrucciones": (
                "Corrige faltas de ortografía: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "texto-correjido",
        },
        {
            "slug": "optimizar_seo",
            "nombre": "Optimizar SEO",
            "instrucciones": (
                "Optimiza para SEO: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "articulo-seo",
        },
        {
            "slug": "crear_titular",
            "nombre": "Crear titular",
            "instrucciones": (
                "Crea un titular atractivo para: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "titular",
        },
        {
            "slug": "resumir_contenido",
            "nombre": "Resumir contenido",
            "instrucciones": (
                "Resume el contenido: {{ texto }}\n\n" +    " Entregas siempre el resultado en el formato exacto que declare la instrucción de la tarea, sin prosa adicional."
            ),
            "modo_ejecucion": "manual",
            "formato_slug": "resumen",
        },
        {
            "slug": "traducir_texto",
            "nombre": "Traducir texto",
            "instrucciones": (
                "Traduce al inglés: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "traduccion",
        },
        {
            "slug": "generar_meta_descripcion",
            "nombre": "Generar meta descripción",
            "instrucciones": (
                "Genera meta descripción para: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "meta-descripcion",
        },
        {
            "slug": "revisar_estilo",
            "nombre": "Revisar estilo",
            "instrucciones": (
                "Revisa el estilo y tono: {{ texto }}\n\n"
                "Entrega un objeto JSON con la estructura del formato de salida asignado. "
                "No incluyas texto fuera del JSON."
            ),
            "modo_ejecucion": "manual",
            "formato_slug": "texto-revisado",
        },
        {
            "slug": "reescritura",
            "nombre": "Reescritura",
            "instrucciones": (
                "Reescribe el siguiente texto aplicando las reglas editoriales: {{ texto }}. "
                +    " Entregas siempre el resultado en el formato exacto que declare la instrucción de la tarea, sin prosa adicional."
            ),
            "modo_ejecucion": "auto",
            "formato_slug": "texto-reescrito",
        },
    ]

    def _siembrar_habilidades(self):
        """Crea FormatoSalida primero, luego Habilidad con instrucciones.
        Retorna (creadas, existentes, actualizadas) y un dict slug->formato."""
        formatos_creados = {}
        for f in self.FORMATOS_SALIDA:
            obj, _ = FormatoSalida.objects.update_or_create(
                slug=f["slug"],
                defaults={
                    "nombre": f["nombre"],
                    "descripcion": f["descripcion"],
                    "esquema": f["esquema"],
                    "version": f["version"],
                    "permite_parcial": f["permite_parcial"],
                    "plantilla_formato": f["plantilla_formato"],
                },
            )
            formatos_creados[f["slug"]] = obj

        creadas = 0
        existentes = 0
        actualizadas = 0
        for h in self.HABILIDADES:
            formato = formatos_creados[h["formato_slug"]]
            obj, created = Habilidad.objects.update_or_create(
                slug=h["slug"],
                defaults={
                    "nombre": h["nombre"],
                    "instrucciones": h["instrucciones"],
                    "modo_ejecucion": h["modo_ejecucion"],
                },
            )
            if created:
                creadas += 1
            else:
                actualizadas += 1
            # Guardar referencia al formato para usar en _siembrar_agentes
            obj._formato_asignado = formato
        return creadas, existentes, actualizadas, formatos_creados

    FORMATO_ROL = (
        " Entregas siempre el resultado en el formato exacto que declare la "
        "instrucción de la tarea (ej. objeto JSON con claves específicas), sin "
        "prosa adicional."
    )

    def _siembrar_agentes(self, modelo, formatos_creados):
        # nombre -> {rol, temperatura, [slugs de habilidades], formato_slug}
        datos = {
            "Investigador": {
                "rol": "Eres un investigador experto." + self.FORMATO_ROL,
                "temperatura": 0.5,
                "habilidades": ["investigar_tema", "resumir_contenido"],
                "formato_slug": "informe-investigacion",
            },
            "Redactor": {
                "rol": "Eres un redactor experto." + self.FORMATO_ROL,
                "temperatura": 0.7,
                "habilidades": ["redactar_articulo", "crear_titular"],
                "formato_slug": "articulo-seo",
            },
            "Editor": {
                "rol": "Eres un editor experto." + self.FORMATO_ROL,
                "temperatura": 0.6,
                "habilidades": ["revision_calidad", "revisar_estilo"],
                "formato_slug": "revision-calidad",
            },
            "SEO": {
                "rol": "Eres un experto en SEO." + self.FORMATO_ROL,
                "temperatura": 0.4,
                "habilidades": [
                    "optimizar_seo",
                    "metadatos_yoast",
                    "generar_meta_descripcion",
                ],
                "formato_slug": "metadatos-seo",
            },
            "Ortografia": {
                "rol": "Eres un corrector de ortografía." + self.FORMATO_ROL,
                "temperatura": 0.3,
                "habilidades": ["corregir_ortografia"],
                "formato_slug": "texto-correjido",
            },
            "Traductor": {
                "rol": "Eres un traductor experto." + self.FORMATO_ROL,
                "temperatura": 0.5,
                "habilidades": ["traducir_texto"],
                "formato_slug": "traduccion",
            },
        }
        habilidades = {h.slug: h for h in Habilidad.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            formato = formatos_creados.get(d["formato_slug"])
            defaults = {
                "rol": d["rol"],
                "temperatura": d["temperatura"],
                "modelo": modelo,
            }
            if formato:
                defaults["formato_salida"] = formato
            obj, created = Agente.objects.get_or_create(
                nombre=nombre,
                defaults=defaults,
            )
            if created:
                creados += 1
            else:
                obj.rol = d["rol"]
                obj.temperatura = d["temperatura"]
                obj.modelo = modelo
                if formato:
                    obj.formato_salida = formato
                obj.save()
                existentes += 1
            obj.habilidades.set(
                [habilidades[s] for s in d["habilidades"] if s in habilidades]
            )
        return creados, existentes

    def _siembrar_equipos(self):
        # nombre -> {descripcion, [nombres de agentes]}
        datos = {
            "Editorial": {
                "descripcion": "Equipo de creación y revisión de contenido editorial.",
                "agentes": ["Investigador", "Redactor", "Editor"],
            },
            "Marketing": {
                "descripcion": "Equipo de contenidos de marketing y SEO.",
                "agentes": ["Redactor", "SEO", "Traductor"],
            },
            "Soporte": {
                "descripcion": "Equipo de soporte y corrección de contenidos.",
                "agentes": ["Investigador", "Ortografia", "Redactor"],
            },
        }
        agentes = {a.nombre: a for a in Agente.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            obj, created = Equipo.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": d["descripcion"]},
            )
            if created:
                creados += 1
            else:
                obj.descripcion = d["descripcion"]
                obj.save()
                existentes += 1
            obj.agentes.set(
                [agentes[a] for a in d["agentes"] if a in agentes]
            )
        return creados, existentes

    def _siembrar_workflows(self):
        # nombre -> {descripcion, equipo, [(orden, slug_habilidad, nombre_agente, modo)]}
        datos = {
            "Publicacion de articulos": {
                "descripcion": "Flujo completo de investigacion y publicacion.",
                "equipo": "Editorial",
                "pasos": [
                    (1, "investigar_tema", "Investigador", "auto"),
                    (2, "redactar_articulo", "Redactor", "auto"),
                    (3, "revisar_estilo", "Editor", "manual"),
                    (4, "metadatos_yoast", "SEO", "auto"),
                ],
            },
            "Adaptacion de contenido": {
                "descripcion": "Flujo de reescritura y optimizacion SEO.",
                "equipo": "Marketing",
                "pasos": [
                    (1, "reescribir_editorial", "Redactor", "auto"),
                    (2, "traducir_texto", "Traductor", "auto"),
                    (3, "optimizar_seo", "SEO", "auto"),
                ],
            },
            "Revision de calidad": {
                "descripcion": "Flujo de correccion y revision final.",
                "equipo": "Editorial",
                "pasos": [
                    (1, "corregir_ortografia", "Ortografia", "auto"),
                    (2, "revision_calidad", "Editor", "manual"),
                ],
            },
            "Creacion de titulares y SEO": {
                "descripcion": "Flujo de titulares y metadatos SEO.",
                "equipo": "Marketing",
                "pasos": [
                    (1, "crear_titular", "Redactor", "auto"),
                    (2, "generar_meta_descripcion", "SEO", "auto"),
                ],
            },
        }
        habilidades = {h.slug: h for h in Habilidad.objects.all()}
        agentes = {a.nombre: a for a in Agente.objects.all()}
        equipos = {e.nombre: e for e in Equipo.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            equipo = equipos.get(d["equipo"])
            workflow, created = Workflow.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "descripcion": d["descripcion"],
                    "estado": "borrador",
                    "equipo": equipo,
                },
            )
            if created:
                creados += 1
            else:
                workflow.descripcion = d["descripcion"]
                workflow.equipo = equipo
                workflow.estado = "borrador"
                workflow.save()
                existentes += 1
            for orden, slug_habilidad, nombre_agente, modo in d["pasos"]:
                habilidad = habilidades.get(slug_habilidad)
                agente = agentes.get(nombre_agente)
                if habilidad is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Saltando paso {orden} de '{nombre}': "
                            f"habilidad '{slug_habilidad}' no encontrada."
                        )
                    )
                    continue
                PasoWorkflow.objects.update_or_create(
                    workflow=workflow,
                    orden=orden,
                    defaults={
                        "habilidad": habilidad,
                        "agente": agente,
                        "modo_ejecucion": modo,
                    },
                )
        return creados, existentes

    def handle(self, *args, **options):
        modelo = self._obtener_modelo()
        if modelo is None:
            self.stdout.write(
                self.style.ERROR(
                    "No existe ningun Proveedor/ModeloLLM disponible. "
                    "Crea al menos uno antes de ejecutar seed_demo."
                )
            )
            sys.exit(1)

        self.stdout.write(
            self.style.NOTICE(
                f"Usando modelo: {modelo.proveedor.nombre} / {modelo.model_id}"
            )
        )

        self._sembrar_skills_sistema(modelo)

        self._sembrar_habilidades_sistema()

        self._sembrar_herramientas_sistema()

        h_creadas, h_exist, h_actualizadas, formatos_creados = (
            self._siembrar_habilidades()
        )
        a_creados, a_exist = self._siembrar_agentes(modelo, formatos_creados)
        e_creados, e_exist = self._siembrar_equipos()
        w_creados, w_exist = self._siembrar_workflows()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Resumen de seed_demo:"))
        self.stdout.write(f"  Habilidades: {h_creadas} creadas, {h_actualizadas} actualizadas, {h_exist} sin cambios.")
        self.stdout.write(f"  Formatos de salida: {len(formatos_creados)} configurados.")
        self.stdout.write(f"  Agentes: {a_creados} creados, {a_exist} ya existían.")
        self.stdout.write(f"  Equipos: {e_creados} creados, {e_exist} ya existían.")
        self.stdout.write(f"  Workflows: {w_creados} creados, {w_exist} ya existían.")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed completado (idempotente)."))
