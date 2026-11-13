"""Tests de extremo a extremo del pipeline editorial, sin red real."""

from __future__ import annotations

import httpx
import pytest
import respx

from apps.core.models import (
    Agente,
    Artefacto,
    Habilidad,
    ModeloLLM,
    Proveedor,
    Tarea,
)
from apps.engine.pipelines import pipeline_editorial

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_CHAT = f"{GEMINI_BASE}/models/gemini-2.0-flash:generateContent"

KEYWORD = "energía solar"
TITULO = "La energía solar en el hogar"
META = (
    "Descubre cómo la energía solar reduce la factura eléctrica, mejora la "
    "eficiencia del hogar y protege el medio ambiente con una instalación "
    "duradera."
)
SLUG = "energia-solar"

TEXTO_SEO = """# La energía solar en el hogar

La luz del sol permite ahorrar en la factura de la luz. El sistema aprovecha
esa luz para producir electricidad. Además, reduce el uso de fuentes
contaminantes. Con una instalación sencilla, una casa puede cubrir parte de su
consumo diario. Por eso, cada vez más familias eligen esta opción. Sus paneles
duran muchos años y requieren poco mantenimiento. Es una alternativa limpia y
práctica para el hogar."""

TEXTO_SEO_CON_VETADA = """# La energía solar en el hogar

La luz del sol permite ahorrar en la factura. El sistema aprovecha esa luz para
producir electricidad. Además, reduce el uso de fuentes contaminantes. Con una
instalación sencilla, una casa puede cubrir parte de su consumo diario. Por eso,
esta opción es crucial para el hogar. Sus paneles duran muchos años y requieren
poco mantenimiento."""


def _respuesta_gemini(texto: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": texto}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 20,
                "candidatesTokenCount": 10,
                "totalTokenCount": 30,
            },
            "modelVersion": "gemini-2.0-flash",
        },
    )


def _crear_escenario(texto_original: str) -> Tarea:
    proveedor = Proveedor.objects.create(
        nombre="gemini",
        base_url=GEMINI_BASE,
        api_key="test-gemini-key",
        limite_diario=100,
    )
    modelo = ModeloLLM.objects.create(
        proveedor=proveedor,
        model_id="gemini-2.0-flash",
        prioridad=1,
    )
    reescritura = Habilidad.objects.create(
        nombre="Reescritura",
        slug="reescritura",
        plantilla_prompt="Reescribe este artículo: {{ texto }}",
        esquema_salida={"type": "object"},
    )
    Habilidad.objects.create(
        nombre="SEO",
        slug="seo",
        plantilla_prompt="Optimiza este artículo: {{ texto }}",
        esquema_salida={"type": "object"},
    )
    agente = Agente.objects.create(
        nombre="Redactor",
        rol="Eres un redactor experto.",
        modelo=modelo,
        temperatura=0.3,
    )
    return Tarea.objects.create(
        agente=agente,
        habilidad=reescritura,
        payload={
            "texto": texto_original,
            "keyword": KEYWORD,
            "titulo": TITULO,
            "meta": META,
            "slug": SLUG,
        },
    )


def _tarea_seo() -> Tarea:
    return Tarea.objects.get(habilidad__slug="seo")


@pytest.mark.django_db
@respx.mock
def test_pipeline_exitoso_termina_en_ok_con_dos_artefactos():
    tarea = _crear_escenario(
        "Texto original uno sobre la energía solar en el hogar."
    )
    ruta = respx.post(GEMINI_CHAT).mock(
        side_effect=[
            _respuesta_gemini("Borrador uno: la energía solar en el hogar."),
            _respuesta_gemini(TEXTO_SEO),
        ]
    )

    resultado = pipeline_editorial(tarea.pk)

    tarea.refresh_from_db()
    seo = _tarea_seo()
    final = seo.artefactos.get()
    assert resultado["estado"] == Tarea.Estado.OK
    assert tarea.estado == Tarea.Estado.OK
    assert ruta.call_count == 2
    assert Artefacto.objects.filter(tarea__in=[tarea, seo]).count() == 2
    assert tarea.artefactos.get().version == 1
    assert final.version == 1
    assert final.metadata["verificacion"] == "ok"
    assert final.metadata["problemas"] == resultado["problemas"]
    assert not [
        problema
        for problema in resultado["problemas"]
        if problema["severidad"] == "alta"
    ]


@pytest.mark.django_db
@respx.mock
def test_pipeline_con_palabra_vetada_termina_en_revision():
    tarea = _crear_escenario(
        "Texto original dos sobre la energía solar en la casa."
    )
    respx.post(GEMINI_CHAT).mock(
        side_effect=[
            _respuesta_gemini("Borrador dos: la energía solar en la casa."),
            _respuesta_gemini(TEXTO_SEO_CON_VETADA),
        ]
    )

    resultado = pipeline_editorial(tarea.pk)

    tarea.refresh_from_db()
    final = _tarea_seo().artefactos.get()
    assert resultado["estado"] == Tarea.Estado.REVISION
    assert tarea.estado == Tarea.Estado.REVISION
    assert final.metadata["verificacion"] == "alta"
    assert any(
        problema["regla"] == "EST-001"
        and problema["severidad"] == "alta"
        for problema in final.metadata["problemas"]
    )


@pytest.mark.django_db
@respx.mock
def test_tarea_seo_depende_de_la_principal():
    tarea = _crear_escenario(
        "Texto original tres sobre la energía solar en el tejado."
    )
    respx.post(GEMINI_CHAT).mock(
        side_effect=[
            _respuesta_gemini("Borrador tres: la energía solar en el tejado."),
            _respuesta_gemini(TEXTO_SEO),
        ]
    )

    pipeline_editorial(tarea.pk)

    tarea.refresh_from_db()
    seo = _tarea_seo()
    assert seo.estado == Tarea.Estado.OK
    assert seo.depende_de.filter(pk=tarea.pk).exists()
    assert tarea.dependientes.filter(pk=seo.pk).exists()
    assert seo.payload["texto"] == tarea.artefactos.get().contenido
    assert seo.payload["keyword"] == KEYWORD
    assert seo.payload["titulo"] == TITULO
    assert seo.payload["meta"] == META
    assert seo.payload["slug"] == SLUG
