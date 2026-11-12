"""Tests de los verificadores deterministas de SEO y estilo."""

import pytest

from apps.checks.estilo import cargar_reglas, verificar_estilo
from apps.checks.seo import verificar_seo

META_VALIDA = "Descripción " * 12  # 144 caracteres.
TEXTO_VALIDO = (
    "# Guía de SEO\n\n"
    "Django permite crear sitios web con poco código. "
    "Es rápido y seguro. "
    "Miles de equipos lo usan cada día. "
    "La comunidad publica guías y ejemplos útiles. "
    "Aprender con práctica mejora el resultado. "
    "Un proyecto pequeño crece paso a paso. "
    "La documentación resuelve dudas comunes. "
    "El código claro ayuda al equipo. "
    "Las pruebas evitan errores. "
    "El plan funciona bien. "
    "El despliegue resulta sencillo."
)
TEXTO_ILEGIBLE = (
    "# Título\n\n"
    "La implementación extraordinaria de funcionalidades tecnológicas "
    "contemporáneas requiere una consideración cuidadosa de las "
    "responsabilidades organizacionales y de la compatibilidad "
    "interinstitucional. "
    "La internacionalización de los procedimientos administrativos "
    "exige una sistematización rigurosa de las metodologías "
    "correspondientes."
)


CASOS_SEO = [
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_VALIDO,
        "django",
        None,
        id="seo-valido",
    ),
    pytest.param(
        "Título " * 10,
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_VALIDO,
        "django",
        "SEO-001",
        id="titulo-largo",
    ),
    pytest.param(
        "Guía práctica de SEO",
        "Descripción " * 11,
        "guia-practica-seo",
        TEXTO_VALIDO,
        "django",
        "SEO-002",
        id="meta-corta",
    ),
    pytest.param(
        "Guía práctica de SEO",
        "Descripción " * 13 + "x",
        "guia-practica-seo",
        TEXTO_VALIDO,
        "django",
        "SEO-002",
        id="meta-larga",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        "# Primero\n\n# Segundo\n\n" + TEXTO_VALIDO,
        "django",
        "SEO-003",
        id="dos-h1",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_VALIDO.split("\n\n", 1)[1],
        "django",
        "SEO-003",
        id="sin-h1",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "Guia-Practica-SEO",
        TEXTO_VALIDO,
        "django",
        "SEO-004",
        id="slug-con-mayusculas",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-de-seo",
        TEXTO_VALIDO,
        "django",
        "SEO-004",
        id="slug-con-stopword",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_VALIDO + " Django Django.",
        "django",
        "SEO-005",
        id="densidad-alta",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_VALIDO,
        "python",
        "SEO-005",
        id="densidad-baja",
    ),
    pytest.param(
        "Guía práctica de SEO",
        META_VALIDA,
        "guia-practica-seo",
        TEXTO_ILEGIBLE,
        "django",
        "SEO-006",
        id="legibilidad-baja",
    ),
]


@pytest.mark.parametrize(
    "titulo,meta,slug,texto,keyword,regla",
    CASOS_SEO,
)
def test_seo_casos(titulo, meta, slug, texto, keyword, regla):
    problemas = verificar_seo(titulo, meta, slug, texto, keyword)

    if regla is None:
        assert problemas == []
        return

    assert regla in {problema["regla"] for problema in problemas}, problemas
    assert all(
        problema["severidad"] in {"alta", "media", "baja"}
        for problema in problemas
    )
    assert all(problema["mensaje"] for problema in problemas)


CASOS_ESTILO = [
    pytest.param(
        "Esta solución es crucial para el equipo.",
        "EST-001",
        "alta",
        id="palabra-vetada",
    ),
    pytest.param(
        "El equipo sirve como puente entre áreas.",
        "EST-002",
        "alta",
        id="frase-vetada",
    ),
    pytest.param(
        "Dijo “hola” al equipo.",
        "EST-003",
        "alta",
        id="comillas-curvas",
    ),
    pytest.param(
        "Compró pan, queso, y vino para la cena.",
        "EST-004",
        "media",
        id="regla-de-tres",
    ),
    pytest.param(
        "- **Paso uno**: abre el archivo.",
        "EST-005",
        "media",
        id="lista-con-negrita",
    ),
    pytest.param(
        "## Cómo mejorar el rendimiento del equipo",
        "EST-005",
        "media",
        id="subtitulo-sin-title-case",
    ),
    pytest.param(
        "**Uno** y **dos** y **tres**.",
        "EST-005",
        "media",
        id="exceso-de-negritas",
    ),
    pytest.param(
        "En conclusión, el proyecto funciona.",
        "EST-005",
        "media",
        id="cierre-vetado",
    ),
    pytest.param(
        "palabra " * 71,
        "EST-006",
        "baja",
        id="parrafo-largo",
    ),
    pytest.param(
        "Esta oración " + "muy " * 39 + "larga.",
        "EST-006",
        "baja",
        id="frase-larga",
    ),
    pytest.param(
        (
            "Uno dos tres cuatro cinco seis siete ocho nueve diez.\n\n"
            "Uno dos tres cuatro cinco seis siete ocho nueve diez.\n\n"
            "Uno dos tres cuatro cinco seis siete ocho nueve diez."
        ),
        "EST-006",
        "baja",
        id="parrafos-similares",
    ),
    pytest.param(
        "El equipo revisó el informe y corrigió los errores.",
        None,
        None,
        id="estilo-valido",
    ),
]


@pytest.mark.parametrize("texto,regla,severidad", CASOS_ESTILO)
def test_estilo_casos(texto, regla, severidad):
    problemas = verificar_estilo(texto)

    if regla is None:
        assert problemas == []
        return

    coincidencias = [
        problema for problema in problemas if problema["regla"] == regla
    ]
    assert coincidencias, problemas
    problema = coincidencias[0]
    assert problema["severidad"] == severidad
    assert isinstance(problema["posicion"], int)
    assert problema["mensaje"]
    assert problema["sugerencia"]


def test_reglas_por_defecto_se_cargan_del_markdown():
    reglas = cargar_reglas()

    assert "crucial" in reglas["palabras_vetadas"]
    assert "sirve como|actúa como|funciona como" in reglas["frases_vetadas"]
    assert "\u201c" in reglas["comillas_curvas"]
    assert reglas["parrafo_max_palabras"] == 70
    assert reglas["frase_max_palabras"] == 40
    assert reglas["negritas_max"] == 2


def test_reglas_se_cargan_desde_una_ruta_alternativa(tmp_path):
    markdown = tmp_path / "estilo.md"
    markdown.write_text(
        "## EST-001 - Palabras vetadas (alta)\n"
        "Lista:\n"
        "prohibida\n\n"
        "## EST-002 - Frases vetadas (alta)\n"
        "Patrones:\n"
        "- frase prohibida\n\n"
        "## EST-003 - Comillas curvas (alta)\n"
        "U+201C y U+201D.\n",
        encoding="utf-8",
    )

    reglas = cargar_reglas(markdown)

    assert reglas["palabras_vetadas"] == ["prohibida"]
    assert reglas["frases_vetadas"] == ["frase prohibida"]
    assert reglas["comillas_curvas"] == ["\u201c", "\u201d"]
