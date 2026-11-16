"""Valores por defecto de los recursos del sistema (es_sistema=True).

Única fuente de verdad para las vistas de restaurar_* y para seed_demo.py.
Los valores se sobrescriben en BD al restaurar o al sembrar datos de demo.
"""

HABILIDADES_SISTEMA = {
    "experto-ui-ux-arm": {
        "nombre": "Experto UI/UX ARM Flow",
        "instrucciones": """Eres un diseñador frontend senior experto en el sistema de diseño 'ARM Flow'. Tu objetivo es traducir conceptos en componentes web semánticos, accesibles y visualmente coherentes.
REGLAS OBLIGATORIAS:
1. Cero estilos inline: Nunca uses el atributo style='...'. Usa exclusivamente las clases y variables CSS de ARM Flow.
2. Paleta intencional: Máximo 3-4 colores con un acento definido. Prohibido gradientes púrpura/azul genéricos o efectos 'glow' sin propósito.
3. Estructura semántica: Usa <article>, <section>, <aside> en lugar de <div> genéricos.
4. Iconografía: Usa sets de iconos SVG profesionales. Nunca uses emojis como iconos de navegación principal.
5. Contenedores con propósito: Usa 'cards' solo para agrupar información relacionada, nunca por decoración.
Si suena a 'plantilla genérica de IA', reescribe la estructura para que sea asimétrica y con propósito humano.""",
        "modo_ejecucion": "auto",
    },
}

FORMATOS_SISTEMA = {
    "componente-ui-arm": {
        "nombre": "Componente UI Estructurado",
        "descripcion": "Estructura de salida para componentes UI del sistema de diseño ARM Flow.",
        "esquema": {
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
        },
        "version": "v1",
        "permite_parcial": False,
        "plantilla_formato": "",
    },
}

HERRAMIENTAS_SISTEMA = {
    "tavily-search": {
        "nombre": "Tavily Search",
        "slug": "tavily-search",
        "tipo": "api",
        "descripcion": "Búsqueda web mediante la API de Tavily.",
        "configuracion": {
            "endpoint": "https://api.tavily.com/search",
            "api_key": "TU_API_KEY_AQUI",
            "search_depth": "advanced",
            "max_results": 5,
            "include_answer": True,
        },
    },
    "wordpress-connector": {
        "nombre": "WordPress Connector",
        "slug": "wordpress-connector",
        "tipo": "api",
        "descripcion": "Publica contenidos en WordPress mediante su API REST.",
        "configuracion": {
            "base_url": "https://tudominio.com/wp-json/wp/v2",
            "username": "TU_USUARIO_WP",
            "app_password": "TU_APP_PASSWORD_WP",
            "estado_defecto": "draft",
        },
    },
    "google-sheets": {
        "nombre": "Google Sheets",
        "slug": "google-sheets",
        "tipo": "api",
        "descripcion": "Lee y escribe datos en una hoja de cálculo de Google Sheets.",
        "configuracion": {
            "spreadsheet_id": "ID_DE_TU_HOJA",
            "sheet_name": "Hoja 1",
            "credentials_json": "PEGA_AQUI_EL_JSON_DE_GOOGLE",
            "accion_defecto": "append",
        },
    },
    "supabase-query": {
        "nombre": "Supabase Query",
        "slug": "supabase-query",
        "tipo": "api",
        "descripcion": "Ejecuta consultas contra una base de datos Supabase.",
        "configuracion": {
            "project_url": "https://TU_PROYECTO.supabase.co",
            "api_key": "TU_SUPABASE_KEY",
            "tabla_defecto": "nombre_tabla",
        },
    },
}
