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
    Proveedor,
    Tarea,
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
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_ok_gemini())

    resultado = tasks.ejecutar_tarea.call_local(tarea.pk)

    tarea.refresh_from_db()
    assert resultado == "ok"
    assert tarea.estado == Tarea.Estado.OK
    assert tarea.intentos == 0


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
