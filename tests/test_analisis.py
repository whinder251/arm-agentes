"""Pruebas del reporte de competencia. Ninguna llamada sale a la red."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.checks.analisis import (
    MAX_HALLAZGOS,
    MENSAJE_SIN_DATOS,
    REGLA_IDIOMA,
    generar_reporte_competencia,
)
from apps.core import defaults
from apps.core.models import (
    Hallazgo,
    Habilidad,
    InvestigacionProgramada,
    ModeloLLM,
    Proveedor,
    Artefacto,
    Agente,
)
from apps.providers.base import CuotaAgotada, RespuestaChat

SLUG = "analista-competencia"


def crear_investigacion(nombre: str = "Competencia") -> InvestigacionProgramada:
    return InvestigacionProgramada.objects.create(
        nombre=nombre,
        urls_objetivo="https://ejemplo.com/feed",
        frecuencia="semanal",
    )


def crear_hallazgos(investigacion: InvestigacionProgramada, cantidad: int = 3):
    return [
        Hallazgo.objects.create(
            investigacion=investigacion,
            url_fuente="https://ejemplo.com/feed",
            tipo_fuente=Hallazgo.TipoFuente.RSS,
            titulo=f"Hallazgo {indice:02d}",
            url_articulo=f"https://ejemplo.com/articulo-{indice}",
            resumen=f"Resumen {indice}",
            contenido_extraido=(
                f"Texto completo del artículo {indice} para análisis profundo."
            ),
        )
        for indice in range(1, cantidad + 1)
    ]


def crear_modelo() -> ModeloLLM:
    proveedor = Proveedor.objects.create(
        nombre="Proveedor Test",
        base_url="https://ejemplo.com",
        api_key="test-api-key-12345",
        tipo_adaptador="gemini",
        limite_diario=10,
    )
    return ModeloLLM.objects.create(
        proveedor=proveedor,
        model_id="modelo-test",
        prioridad=1,
    )


def respuesta_markdown() -> RespuestaChat:
    return RespuestaChat(
        texto="# Reporte\n\n## Resumen\nContenido del reporte.",
        tokens_in=10,
        tokens_out=20,
        modelo="modelo-test",
    )


@pytest.mark.django_db
def test_generar_reporte_construye_prompt_y_llama_una_vez():
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, 3)
    crear_modelo()
    Habilidad.objects.create(
        nombre="Analista de Competencia",
        slug=SLUG,
        instrucciones="Prompt personalizado de prueba.",
        modo_ejecucion="auto",
    )
    esperada = respuesta_markdown()

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = esperada
        resultado = generar_reporte_competencia(investigacion.pk)

    assert resultado["reporte"] == esperada.texto
    assert resultado["artefacto_id"] is not None
    router_cls.assert_called_once()
    router_cls.return_value.completar.assert_called_once()

    artefacto = Artefacto.objects.get(id=resultado["artefacto_id"])
    assert artefacto.contenido == esperada.texto
    assert artefacto.metadata["investigacion_id"] == investigacion.pk

    modelos = router_cls.call_args.args[0]
    assert len(modelos) == 1
    mensajes = router_cls.return_value.completar.call_args.args[0]
    assert mensajes[0] == {
        "role": "system",
        "content": "Prompt personalizado de prueba." + REGLA_IDIOMA,
    }
    assert mensajes[1]["role"] == "user"
    assert "Hallazgo 01" in mensajes[1]["content"]
    assert "Hallazgo 02" in mensajes[1]["content"]
    assert "Hallazgo 03" in mensajes[1]["content"]
    assert "URL: https://ejemplo.com/articulo-1" in mensajes[1]["content"]
    assert "Texto completo del artículo 1 para análisis profundo." in mensajes[1]["content"]
    assert "Contenido: " in mensajes[1]["content"]
    assert "Resumen 01" not in mensajes[1]["content"]
    assert mensajes[1]["content"].count("- [rss]") == 3


@pytest.mark.django_db
def test_usa_prompt_de_defaults_si_no_existe_la_habilidad():
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, 3)
    crear_modelo()

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        generar_reporte_competencia(investigacion.pk)

    mensajes = router_cls.return_value.completar.call_args.args[0]
    assert mensajes[0]["content"] == (
        defaults.HABILIDADES_SISTEMA[SLUG]["instrucciones"] + REGLA_IDIOMA
    )


@pytest.mark.django_db
def test_sin_hallazgos_devuelve_mensaje_sin_llamar_al_llm():
    investigacion = crear_investigacion()

    with patch("apps.checks.analisis.Router") as router_cls:
        resultado = generar_reporte_competencia(investigacion.pk)

    assert resultado["reporte"] == MENSAJE_SIN_DATOS
    assert resultado["artefacto_id"] is None
    router_cls.assert_not_called()


@pytest.mark.django_db
def test_sin_modelos_activos_devuelve_mensaje_sin_llamar_al_llm():
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, 3)

    with patch("apps.checks.analisis.Router") as router_cls:
        resultado = generar_reporte_competencia(investigacion.pk)

    assert "No hay modelos de IA activos" in resultado["reporte"]
    router_cls.assert_not_called()


@pytest.mark.django_db
def test_error_del_llm_devuelve_mensaje_markdown_legible():
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, 3)
    crear_modelo()

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.side_effect = CuotaAgotada(
            "sin cuota diaria"
        )
        resultado = generar_reporte_competencia(investigacion.pk)

    assert "## No se pudo generar el reporte" in resultado["reporte"]
    assert "Error al contactar al LLM: sin cuota diaria" in resultado["reporte"]
    assert resultado["artefacto_id"] is None


@pytest.mark.django_db
def test_limita_a_quince_hallazgos():
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, MAX_HALLAZGOS + 1)
    crear_modelo()

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        generar_reporte_competencia(investigacion.pk)

    contenido = router_cls.return_value.completar.call_args.args[0][1]["content"]
    assert "Hallazgo 16" in contenido
    assert "Hallazgo 01" not in contenido
    assert contenido.count("- [rss]") == MAX_HALLAZGOS


@pytest.mark.django_db
def test_investigacion_inexistente_devuelve_mensaje():
    resultado = generar_reporte_competencia(999999)

    assert "No se encontró la investigación indicada" in resultado["reporte"]
    assert resultado["artefacto_id"] is None


@pytest.mark.django_db
def test_seed_demo_crea_habilidad_analista_de_competencia():
    crear_modelo()

    call_command("seed_demo")
    call_command("seed_demo")

    habilidad = Habilidad.objects.get(slug=SLUG)
    assert habilidad.es_sistema is True
    assert habilidad.modo_ejecucion == "auto"
    assert habilidad.instrucciones == (
        defaults.HABILIDADES_SISTEMA[SLUG]["instrucciones"]
    )
    assert Habilidad.objects.filter(slug=SLUG).count() == 1


@pytest.mark.django_db
def test_generar_reporte_crea_artefacto_con_metadata():
    """Tras generar, existe un Artefacto con el contenido y el vínculo a la investigación."""
    investigacion = crear_investigacion()
    crear_hallazgos(investigacion, 3)
    crear_modelo()
    Habilidad.objects.create(
        nombre="Analista de Competencia",
        slug=SLUG,
        instrucciones="Prompt de prueba.",
        modo_ejecucion="auto",
    )

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        resultado = generar_reporte_competencia(investigacion.pk)

    assert resultado["artefacto_id"] is not None
    artefacto = Artefacto.objects.get(id=resultado["artefacto_id"])
    assert artefacto.contenido == "# Reporte\n\n## Resumen\nContenido del reporte."
    assert artefacto.metadata["investigacion_id"] == investigacion.pk


@pytest.mark.django_db
def test_usa_modelo_del_agente_y_concatena_todas_las_habilidades():
    """Con agente con modelo propio y dos habilidades, el Router recibe el
    modelo del agente (no el global) y el prompt del sistema concatena
    rol + instrucciones de todas las habilidades + REGLA_IDIOMA al final."""
    modelo_agente = crear_modelo()
    habilidad_1 = Habilidad.objects.create(
        nombre="Habilidad A",
        slug="habilidad-a-test",
        instrucciones="Tono profesional y extenso.",
        modo_ejecucion="auto",
    )
    habilidad_2 = Habilidad.objects.create(
        nombre="Habilidad B",
        slug="habilidad-b-test",
        instrucciones="Entregable en formato Markdown.",
        modo_ejecucion="auto",
    )
    agente = Agente.objects.create(
        nombre="Agente Analista",
        modelo=modelo_agente,
        rol="Eres un analista experto.",
        temperatura=0.7,
    )
    agente.habilidades.add(habilidad_1, habilidad_2)
    investigacion = InvestigacionProgramada.objects.create(
        nombre="Con agente",
        urls_objetivo="https://ejemplo.com/feed",
        frecuencia="semanal",
        agente=agente,
    )
    crear_hallazgos(investigacion, 3)

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        generar_reporte_competencia(investigacion.pk)

    assert router_cls.called
    modelos = router_cls.call_args.args[0]
    assert modelos == [modelo_agente]
    mensajes = router_cls.return_value.completar.call_args.args[0]
    contenido = mensajes[0]["content"]
    assert "Eres un analista experto." in contenido
    assert "Tono profesional y extenso." in contenido
    assert "Entregable en formato Markdown." in contenido
    assert REGLA_IDIOMA in contenido
    assert contenido.index("Tono profesional y extenso.") < contenido.index(
        "Entregable en formato Markdown."
    )
    assert contenido.rstrip().endswith(REGLA_IDIOMA)


@pytest.mark.django_db
def test_agente_sin_modelo_devuelve_error_sin_llamar_router():
    """Agente sin modelo: devuelve mensaje claro, artefacto_id None y no llama al Router."""
    agente = Agente.objects.create(
        nombre="Agente Sin Modelo",
        modelo=None,
        rol="Eres un analista.",
        temperatura=0.7,
    )
    investigacion = InvestigacionProgramada.objects.create(
        nombre="Agente sin modelo",
        urls_objetivo="https://ejemplo.com/feed",
        frecuencia="semanal",
        agente=agente,
    )
    crear_hallazgos(investigacion, 3)

    with patch("apps.checks.analisis.Router") as router_cls:
        resultado = generar_reporte_competencia(investigacion.pk)

    assert resultado["artefacto_id"] is None
    assert "El agente asignado no tiene modelo" in resultado["reporte"]
    assert "Asígnale uno en el panel de Agentes." in resultado["reporte"]
    router_cls.assert_not_called()


@pytest.mark.django_db
def test_inyecta_palabras_clave_en_prompt_usuario():
    """Las palabras clave de la investigación se inyectan en el prompt de usuario."""
    crear_modelo()
    investigacion = InvestigacionProgramada.objects.create(
        nombre="Con palabras clave",
        urls_objetivo="https://ejemplo.com/feed",
        frecuencia="semanal",
        palabras_clave="seo, tendencia, competencia",
    )
    crear_hallazgos(investigacion, 3)
    Habilidad.objects.create(
        nombre="Analista de Competencia",
        slug=SLUG,
        instrucciones="Prompt de prueba.",
        modo_ejecucion="auto",
    )

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        generar_reporte_competencia(investigacion.pk)

    mensajes = router_cls.return_value.completar.call_args.args[0]
    contenido = mensajes[1]["content"]
    assert "ENFOQUE DEL ANÁLISIS" in contenido
    assert "seo, tendencia, competencia" in contenido


@pytest.mark.django_db
def test_formato_auditoria_si_palabras_clave_coinciden():
    """Las palabras clave tipo SEO/diseño activan el formato de auditoría en el prompt del sistema."""
    crear_modelo()
    investigacion = InvestigacionProgramada.objects.create(
        nombre="Auditoría SEO",
        urls_objetivo="https://ejemplo.com/feed",
        frecuencia="semanal",
        palabras_clave="seo, diseño",
    )
    crear_hallazgos(investigacion, 3)
    Habilidad.objects.create(
        nombre="Analista de Competencia",
        slug=SLUG,
        instrucciones="Prompt de prueba.",
        modo_ejecucion="auto",
    )

    with patch("apps.checks.analisis.Router") as router_cls:
        router_cls.return_value.completar.return_value = respuesta_markdown()
        generar_reporte_competencia(investigacion.pk)

    mensajes = router_cls.return_value.completar.call_args.args[0]
    assert "FORMATO DE SALIDA" in mensajes[0]["content"]
    assert "Hallazgos Críticos" in mensajes[0]["content"]
