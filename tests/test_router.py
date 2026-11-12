"""Tests del router con caché y fallback. Ninguna llamada sale a la red."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.core.models import ContadorCuota, ModeloLLM, Proveedor
from apps.providers.base import CuotaAgotada, RespuestaChat
from apps.providers.cache import CacheRespuestas
from apps.providers.router import Router

FIXTURES = Path(__file__).parent / "fixtures"

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GEMINI_CHAT = f"{GEMINI_BASE}/models/gemini-2.0-flash:generateContent"
OPENROUTER_CHAT = f"{OPENROUTER_BASE}/chat/completions"

MESSAGES = [{"role": "user", "content": "¿Cuál es la capital de Francia?"}]
EXPECTED_TEXT = "La capital de Francia es París."


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def crear_proveedor(nombre: str, limite_diario: int = 5) -> Proveedor:
    base_url = GEMINI_BASE if nombre == "gemini" else OPENROUTER_BASE
    return Proveedor.objects.create(
        nombre=nombre,
        base_url=base_url,
        api_key=f"test-{nombre}-key",
        limite_diario=limite_diario,
    )


def crear_modelo(
    proveedor: Proveedor, model_id: str, prioridad: int
) -> ModeloLLM:
    return ModeloLLM.objects.create(
        proveedor=proveedor,
        model_id=model_id,
        prioridad=prioridad,
    )


def dos_modelos() -> list[ModeloLLM]:
    gemini = crear_modelo(crear_proveedor("gemini"), "gemini-2.0-flash", 1)
    openrouter = crear_modelo(
        crear_proveedor("openrouter"), "openrouter/auto", 2
    )
    return [gemini, openrouter]


def respuesta_ok_gemini() -> httpx.Response:
    return httpx.Response(200, json=load_fixture("gemini_chat_200.json"))


def respuesta_ok_openrouter() -> httpx.Response:
    return httpx.Response(200, json=load_fixture("openrouter_chat_200.json"))


def respuesta_429_gemini() -> httpx.Response:
    return httpx.Response(429, json=load_fixture("gemini_chat_429.json"))


def respuesta_429_openrouter() -> httpx.Response:
    return httpx.Response(429, json=load_fixture("openrouter_chat_429.json"))


@pytest.mark.django_db
@respx.mock
def test_segunda_llamada_identica_sale_de_cache():
    peticion = respx.post(GEMINI_CHAT).mock(
        return_value=respuesta_ok_gemini()
    )
    modelos = dos_modelos()

    router = Router(modelos)
    primera = router.completar(MESSAGES)
    segunda = router.completar(MESSAGES)

    assert primera == segunda
    assert segunda.texto == EXPECTED_TEXT
    assert len(peticion.calls) == 1
    # El acierto de caché no gasta cuota: una única reserva para dos llamadas.
    contador = ContadorCuota.objects.get(proveedor=modelos[0].proveedor)
    assert contador.usadas == 1


@pytest.mark.django_db
@respx.mock
def test_429_del_primer_modelo_cae_al_segundo():
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_429_gemini())
    respx.post(OPENROUTER_CHAT).mock(
        return_value=respuesta_ok_openrouter()
    )

    respuesta = Router(dos_modelos()).completar(MESSAGES)

    assert respuesta.modelo == "openrouter/auto"
    assert respuesta.texto == EXPECTED_TEXT


@pytest.mark.django_db
@respx.mock
def test_si_todos_fallan_con_429_lanza_cuota_agotada():
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_429_gemini())
    respx.post(OPENROUTER_CHAT).mock(return_value=respuesta_429_openrouter())

    with pytest.raises(CuotaAgotada):
        Router(dos_modelos()).completar(MESSAGES)


@pytest.mark.django_db
@respx.mock
def test_el_fallback_no_consume_cuota_del_proveedor_que_fallo():
    respx.post(GEMINI_CHAT).mock(return_value=respuesta_429_gemini())
    respx.post(OPENROUTER_CHAT).mock(
        return_value=respuesta_ok_openrouter()
    )
    modelos = dos_modelos()

    Router(modelos).completar(MESSAGES)

    fallido = ContadorCuota.objects.get(proveedor=modelos[0].proveedor)
    usado = ContadorCuota.objects.get(proveedor=modelos[1].proveedor)
    assert fallido.usadas == 0
    assert usado.usadas == 1


@pytest.mark.django_db
@respx.mock
def test_el_429_deja_el_modelo_en_espera_sesenta_segundos():
    gemini = respx.post(GEMINI_CHAT).mock(
        return_value=respuesta_429_gemini()
    )
    # Un 5xx no activa la espera: solo el 429 la justifica.
    openrouter = respx.post(OPENROUTER_CHAT).mock(
        return_value=httpx.Response(
            500, json={"error": {"code": 500, "message": "Internal error"}}
        )
    )
    router = Router(dos_modelos(), reloj=lambda: 0.0)

    with pytest.raises(CuotaAgotada):
        router.completar(MESSAGES)
    with pytest.raises(CuotaAgotada):
        router.completar(MESSAGES)

    assert len(gemini.calls) == 1
    assert len(openrouter.calls) == 2


@pytest.mark.django_db
def test_cache_guarda_y_distingue_configuracion():
    cache = CacheRespuestas()
    respuesta = RespuestaChat(
        texto="hola", tokens_in=3, tokens_out=4, modelo="gemini-2.0-flash"
    )

    cache.set(MESSAGES, "gemini-2.0-flash", {"temperature": 0.2}, respuesta)

    guardada = cache.get(MESSAGES, "gemini-2.0-flash", {"temperature": 0.2})
    assert guardada == respuesta
    assert cache.get(MESSAGES, "gemini-2.0-flash", {"temperature": 0.7}) is None
