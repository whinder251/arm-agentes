"""Tests de los adaptadores de proveedores. Ninguna llamada sale a la red."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.providers.base import (
    ErrorServidor,
    LimiteVelocidad,
    TimeoutProveedor,
)
from apps.providers.gemini import GeminiProvider
from apps.providers.openrouter import OpenRouterProvider

FIXTURES = Path(__file__).parent / "fixtures"

GEMINI_CHAT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)
GEMINI_MODELS = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"

MESSAGES = [{"role": "user", "content": "¿Cuál es la capital de Francia?"}]
EXPECTED_TEXT = "La capital de Francia es París."


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@respx.mock
def test_gemini_200_normaliza_texto_y_tokens():
    respx.post(GEMINI_CHAT).mock(
        return_value=httpx.Response(200, json=load_fixture("gemini_chat_200.json"))
    )

    with GeminiProvider(api_key="test-gemini-key") as provider:
        result = provider.chat(MESSAGES, "gemini-2.0-flash")

    assert result.texto == EXPECTED_TEXT
    assert result.tokens_in == 21
    assert result.tokens_out == 9
    assert result.modelo == "gemini-2.0-flash"


@respx.mock
def test_gemini_429_lanza_limite_velocidad():
    respx.post(GEMINI_CHAT).mock(
        return_value=httpx.Response(429, json=load_fixture("gemini_chat_429.json"))
    )

    with GeminiProvider(api_key="test-gemini-key") as provider:
        with pytest.raises(LimiteVelocidad):
            provider.chat(MESSAGES, "gemini-2.0-flash")


@respx.mock
def test_gemini_500_lanza_error_servidor():
    respx.post(GEMINI_CHAT).mock(
        return_value=httpx.Response(
            500, json={"error": {"code": 500, "message": "Internal error"}}
        )
    )

    with GeminiProvider(api_key="test-gemini-key") as provider:
        with pytest.raises(ErrorServidor):
            provider.chat(MESSAGES, "gemini-2.0-flash")


@respx.mock
def test_gemini_timeout_lanza_timeout_proveedor():
    respx.post(GEMINI_CHAT).mock(side_effect=httpx.ReadTimeout("timeout simulado"))

    with GeminiProvider(api_key="test-gemini-key") as provider:
        with pytest.raises(TimeoutProveedor):
            provider.chat(MESSAGES, "gemini-2.0-flash")


@respx.mock
def test_gemini_normaliza_mensajes_y_config():
    route = respx.post(GEMINI_CHAT).mock(
        return_value=httpx.Response(200, json=load_fixture("gemini_chat_200.json"))
    )
    messages = [
        {"role": "system", "content": "Responde en español"},
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "¿Qué tal?"},
    ]

    with GeminiProvider(api_key="test-gemini-key") as provider:
        provider.chat(
            messages,
            "gemini-2.0-flash",
            {"temperature": 0.2, "max_tokens": 64},
        )

    sent = json.loads(route.calls[0].request.content)
    assert sent["systemInstruction"]["parts"][0]["text"] == "Responde en español"
    assert sent["contents"] == [
        {"role": "user", "parts": [{"text": "Hola"}]},
        {"role": "model", "parts": [{"text": "¿Qué tal?"}]},
    ]
    assert sent["generationConfig"] == {
        "temperature": 0.2,
        "maxOutputTokens": 64,
    }
    assert route.calls[0].request.headers["x-goog-api-key"] == "test-gemini-key"


@respx.mock
def test_gemini_get_models_y_validate_connection():
    respx.get(GEMINI_MODELS).mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-2.0-flash"},
                    {"name": "models/gemini-2.5-flash"},
                ]
            },
        )
    )

    with GeminiProvider(api_key="test-gemini-key") as provider:
        assert provider.get_models() == [
            "gemini-2.0-flash",
            "gemini-2.5-flash",
        ]
        assert provider.validate_connection() is True


@respx.mock
def test_openrouter_200_normaliza_texto_y_tokens():
    respx.post(OPENROUTER_CHAT).mock(
        return_value=httpx.Response(
            200, json=load_fixture("openrouter_chat_200.json")
        )
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        result = provider.chat(MESSAGES, "openrouter/auto")

    assert result.texto == EXPECTED_TEXT
    assert result.tokens_in == 21
    assert result.tokens_out == 9
    assert result.modelo == "openrouter/auto"


@respx.mock
def test_openrouter_429_lanza_limite_velocidad():
    respx.post(OPENROUTER_CHAT).mock(
        return_value=httpx.Response(
            429, json=load_fixture("openrouter_chat_429.json")
        )
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        with pytest.raises(LimiteVelocidad):
            provider.chat(MESSAGES, "openrouter/auto")


@respx.mock
def test_openrouter_500_lanza_error_servidor():
    respx.post(OPENROUTER_CHAT).mock(
        return_value=httpx.Response(
            500, json={"error": {"code": 500, "message": "Internal error"}}
        )
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        with pytest.raises(ErrorServidor):
            provider.chat(MESSAGES, "openrouter/auto")


@respx.mock
def test_openrouter_timeout_lanza_timeout_proveedor():
    respx.post(OPENROUTER_CHAT).mock(
        side_effect=httpx.ReadTimeout("timeout simulado")
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        with pytest.raises(TimeoutProveedor):
            provider.chat(MESSAGES, "openrouter/auto")


@respx.mock
def test_openrouter_pasa_config_y_credencial():
    route = respx.post(OPENROUTER_CHAT).mock(
        return_value=httpx.Response(
            200, json=load_fixture("openrouter_chat_200.json")
        )
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        provider.chat(
            MESSAGES,
            "openrouter/auto",
            {"temperature": 0.2, "max_tokens": 64},
        )

    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "openrouter/auto"
    assert sent["messages"] == MESSAGES
    assert sent["temperature"] == 0.2
    assert sent["max_tokens"] == 64
    assert (
        route.calls[0].request.headers["authorization"]
        == "Bearer test-openrouter-key"
    )


@respx.mock
def test_openrouter_get_models_y_validate_connection():
    respx.get(OPENROUTER_MODELS).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": "anthropic/claude-3.5-sonnet"},
                    {"id": "openai/gpt-4o-mini"},
                ]
            },
        )
    )

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        assert provider.get_models() == [
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o-mini",
        ]
        assert provider.validate_connection() is True


def test_get_usage_normaliza_tokens_entre_proveedores():
    gemini_data = load_fixture("gemini_chat_200.json")
    openrouter_data = load_fixture("openrouter_chat_200.json")

    with GeminiProvider(api_key="test-gemini-key") as provider:
        assert provider.get_usage(gemini_data) == {
            "tokens_in": 21,
            "tokens_out": 9,
        }

    with OpenRouterProvider(api_key="test-openrouter-key") as provider:
        assert provider.get_usage(openrouter_data) == {
            "tokens_in": 21,
            "tokens_out": 9,
        }
