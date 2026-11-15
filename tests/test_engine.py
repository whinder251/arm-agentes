"""Tests del motor de ejecución. Ninguna llamada sale a la red."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
import respx
from django.utils import timezone

from apps.core.models import (
    Agente,
    Artefacto,
    Ejecucion,
    Habilidad,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Tarea,
    Workflow,
)
from apps.engine import tasks

FIXTURES = Path(__file__).parent / "fixtures"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_CHAT = f"{GEMINI_BASE}/models/gemini-2.0-flash:generateContent"
TEXTO_ESPERADO = "La capital de Francia es París."


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def crear_escenario() -> Tarea:
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
    habilidad = Habilidad.objects.create(
        nombre="SEO",
        slug="seo",
        plantilla_prompt="Reescribe el texto: {{ texto }}",
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
        habilidad=habilidad,
        payload={"texto": "Artículo original"},
    )


def respuesta_ok_gemini() -> httpx.Response:
    return httpx.Response(200, json=load_fixture("gemini_chat_200.json"))


def respuesta_429_gemini() -> httpx.Response:
    return httpx.Response(429, json=load_fixture("gemini_chat_429.json"))


@pytest.mark.django_db
@respx.mock
def test_ejecutar_tarea_termina_en_ok():
    tarea = crear_escenario()
    payload_json = json.dumps({
        "titulo": "La capital de Francia",
        "contenido": "París es la capital de Francia.",
    })
    respx.post(GEMINI_CHAT).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": payload_json}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        "modelVersion": "gemini-2.0-flash",
    }))

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "ok"
    assert tarea.estado == Tarea.Estado.OK
    assert tarea.intentos == 0


@pytest.mark.django_db
@respx.mock
def test_tarea_falla_cuando_normalizador_falla():
    """Cuando el modelo no devuelve JSON válido, el normalizador marca
    status="failed" y la tarea queda en estado ERROR."""
    tarea = crear_escenario()
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_ok_gemini())

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "error"
    assert tarea.estado == Tarea.Estado.ERROR


@pytest.mark.django_db
@respx.mock
def test_tarea_revision_cuando_modo_manual():
    """Si modo_ejecucion=="manual", la tarea queda en REVISION y no
    se crea la siguiente tarea del workflow."""
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
    habilidad_manual = Habilidad.objects.create(
        nombre="Manual",
        slug="manual",
        plantilla_prompt="Haz algo: {{ texto }}",
        esquema_salida={"type": "object"},
        modo_ejecucion="manual",
    )
    agente = Agente.objects.create(
        nombre="Agente Manual",
        rol="Eres un agente.",
        modelo=modelo,
        temperatura=0.3,
    )
    workflow = Workflow.objects.create(
        nombre="W manual",
        descripcion="Flujo con paso manual",
        estado="en_ejecucion",
    )
    paso1 = PasoWorkflow.objects.create(
        workflow=workflow,
        orden=1,
        habilidad=habilidad_manual,
        agente=agente,
    )
    paso2 = PasoWorkflow.objects.create(
        workflow=workflow,
        orden=2,
        habilidad=habilidad_manual,
        agente=agente,
    )

    payload_json = json.dumps({"contenido": "resultado manual"})
    respx.post(GEMINI_CHAT).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": payload_json}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        "modelVersion": "gemini-2.0-flash",
    }))

    resultado = tasks.ejecutar_tarea.call_local(
        Tarea.objects.create(
            agente=agente,
            habilidad=habilidad_manual,
            payload={"texto": "x"},
            paso_workflow=paso1,
        ).pk
    )

    tarea = Tarea.objects.get(paso_workflow=paso1)
    tarea.refresh_from_db()
    assert resultado == "revision"
    assert tarea.estado == Tarea.Estado.REVISION
    # El workflow no debe haber continuado: no existe tarea del paso 2.
    assert Tarea.objects.filter(paso_workflow=paso2).count() == 0


@pytest.mark.django_db
@respx.mock
def test_fallo_del_proveedor_reencola_tres_veces_y_luego_falla(monkeypatch):
    tarea = crear_escenario()
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_429_gemini())
    reencoladas: list[tuple[int, int]] = []

    def reencolar(tarea_id: int, intento: int) -> None:
        reencoladas.append((tarea_id, intento))

    monkeypatch.setattr(tasks, "programar_reintento", reencolar)

    for _ in range(4):
        tasks.ejecutar_tarea.call_local(tarea.pk)
        tarea.refresh_from_db()
        if tarea.estado == Tarea.Estado.FALLO:
            break
        assert tarea.estado == Tarea.Estado.COLA

    assert tarea.estado == Tarea.Estado.FALLO
    assert tarea.intentos == 3
    assert [intento for _, intento in reencoladas] == [1, 2, 3]
    assert all(tarea_id == tarea.pk for tarea_id, _ in reencoladas)
    assert Ejecucion.objects.filter(tarea=tarea, error__contains="ningún modelo").count() == 4
    assert Artefacto.objects.filter(tarea=tarea).count() == 0


@pytest.mark.django_db
def test_tarea_huerfana_se_reencola(monkeypatch):
    tarea = crear_escenario()
    Tarea.objects.filter(pk=tarea.pk).update(
        estado=Tarea.Estado.CURSO,
        actualizado_en=timezone.now() - timedelta(minutes=6),
    )
    reencoladas: list[int] = []
    monkeypatch.setattr(
        tasks,
        "programar_reintento",
        lambda tarea_id, intento: reencoladas.append(intento),
    )

    recuperadas = tasks.recuperar_huerfanas()

    tarea.refresh_from_db()
    assert recuperadas == 1
    assert tarea.estado == Tarea.Estado.COLA
    assert tarea.intentos == 1
    assert reencoladas == [1]


@pytest.mark.django_db
@respx.mock
def test_ejecucion_y_artefacto_se_crean():
    tarea = crear_escenario()
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_ok_gemini())

    tasks.ejecutar_tarea.call_local(tarea.pk)

    ejecucion = Ejecucion.objects.get(tarea=tarea)
    artefacto = Artefacto.objects.get(tarea=tarea)
    assert ejecucion.modelo_usado == "gemini-2.0-flash"
    assert ejecucion.tokens_in == 21
    assert ejecucion.tokens_out == 9
    assert ejecucion.salida["texto"] == TEXTO_ESPERADO
    assert ejecucion.error == ""
    assert artefacto.version == 1
    assert artefacto.contenido == TEXTO_ESPERADO
    assert artefacto.metadata["modelo"] == "gemini-2.0-flash"
    assert artefacto.metadata["ejecucion"] == ejecucion.pk


@pytest.mark.django_db
@respx.mock
def test_artefacto_guarda_metadata_estructurado_desde_json():
    """Cuando la habilidad tiene esquema_salida y el modelo responde JSON válido,
    el artefacto guarda las claves nombradas en metadata."""
    tarea = crear_escenario()
    payload_json = json.dumps({
        "titulo": "La capital de Francia",
        "slug": "la-capital-de-francia",
        "contenido": "París es la capital de Francia.",
        "meta_description": "Descubre cuál es la capital de Francia.",
        "focus_keyword": "París",
    })
    respx.post(GEMINI_CHAT).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": payload_json}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        "modelVersion": "gemini-2.0-flash",
    }))

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "ok"
    artefacto = Artefacto.objects.get(tarea=tarea)
    assert artefacto.metadata["titulo"] == "La capital de Francia"
    assert artefacto.metadata["slug"] == "la-capital-de-francia"
    assert artefacto.metadata["contenido"] == "París es la capital de Francia."
    assert artefacto.metadata["meta_description"] == "Descubre cuál es la capital de Francia."
    assert artefacto.metadata["focus_keyword"] == "París"
    assert artefacto.metadata["modelo"] == "gemini-2.0-flash"
    assert artefacto.metadata["ejecucion"] is not None


@pytest.mark.django_db
@respx.mock
def test_artefacto_guarda_texto_plano_cuando_respuesta_no_es_json():
    """Si la respuesta no es JSON válido, el normalizador marca status="failed",
    la tarea queda en ERROR y el artefacto guarda texto plano en
    metadata['contenido'] sin romper el flujo."""
    tarea = crear_escenario()
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_ok_gemini())

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "error"
    assert tarea.estado == Tarea.Estado.ERROR
    artefacto = Artefacto.objects.get(tarea=tarea)
    assert artefacto.metadata["contenido"] == TEXTO_ESPERADO
    assert artefacto.metadata["modelo"] == "gemini-2.0-flash"
    assert artefacto.contenido == TEXTO_ESPERADO


@pytest.mark.django_db
@respx.mock
def test_artefacto_extrae_cuerpo_cuando_json_no_tiene_contenido():
    """Cuando el modelo devuelve JSON válido con 'cuerpo' pero sin 'contenido',
    el artefacto guarda el texto de 'cuerpo' en contenido y metadata."""
    tarea = crear_escenario()
    payload_json = json.dumps({
        "titulo": "Título reescrito",
        "cuerpo": "Este es el texto reescrito sin la clave contenido.",
    })
    respx.post(GEMINI_CHAT).mock(return_value=httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": payload_json}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        "modelVersion": "gemini-2.0-flash",
    }))

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "ok"
    artefacto = Artefacto.objects.get(tarea=tarea)
    assert artefacto.contenido == "Este es el texto reescrito sin la clave contenido."
    assert artefacto.metadata["contenido"] == "Este es el texto reescrito sin la clave contenido."
    assert artefacto.metadata["titulo"] == "Título reescrito"


@pytest.mark.django_db
def test_workflow_pasa_datos_entre_pasos(monkeypatch):
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
    habilidad_investigar = Habilidad.objects.create(
        nombre="Investigar",
        slug="investigar",
        plantilla_prompt="Investiga: {{ tema }}",
        esquema_salida={},
    )
    habilidad_redactar = Habilidad.objects.create(
        nombre="Redactar",
        slug="redactar",
        plantilla_prompt="Redacta: {{ hallazgos }}",
        esquema_salida={},
    )
    agente = Agente.objects.create(
        nombre="Agente",
        rol="Eres un agente.",
        modelo=modelo,
        temperatura=0.3,
    )
    workflow = Workflow.objects.create(
        nombre="W1",
        descripcion="Flujo de prueba",
        estado="en_ejecucion",
    )
    paso1 = PasoWorkflow.objects.create(
        workflow=workflow,
        orden=1,
        habilidad=habilidad_investigar,
        agente=agente,
    )
    paso2 = PasoWorkflow.objects.create(
        workflow=workflow,
        orden=2,
        habilidad=habilidad_redactar,
        agente=agente,
    )
    tarea1 = Tarea.objects.create(
        agente=agente,
        habilidad=habilidad_investigar,
        estado=Tarea.Estado.OK,
        payload={},
        paso_workflow=paso1,
    )
    Artefacto.objects.create(
        tarea=tarea1,
        version=1,
        contenido="contenido del paso 1",
        metadata={
            "modelo": "gemini",
            "tokens_in": 10,
            "tokens_out": 5,
            "ejecucion": 1,
            "resultado": {
                "success": True,
                "status": "completed",
                "data": {"hallazgos": ["dato1", "dato2"]},
                "error": None,
                "metadata": {},
            },
        },
    )

    monkeypatch.setattr(tasks, "ejecutar_tarea", lambda pk: None)

    resultado = tasks.continuar_workflow.call_local(workflow.pk, 2)

    assert resultado == "encolado"
    tarea2 = Tarea.objects.get(paso_workflow=paso2)
    assert tarea2.payload == {"hallazgos": ["dato1", "dato2"]}
