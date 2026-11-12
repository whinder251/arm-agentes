"""Adaptador para OpenRouter, compatible con la API de OpenAI."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from apps.providers.base import (
    BaseProveedor,
    ErrorProveedor,
    Messages,
    RespuestaChat,
)


class OpenRouterProvider(BaseProveedor):
    """Proveedor OpenRouter sobre chat/completions."""

    nombre = "openrouter"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )

    def chat(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> RespuestaChat:
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": list(messages),
        }
        config = config or {}
        if "temperature" in config:
            payload["temperature"] = config["temperature"]
        if "max_tokens" in config:
            payload["max_tokens"] = config["max_tokens"]
        response = self._request(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        )
        data = response.json()
        usage = self.get_usage(data)
        return RespuestaChat(
            texto=self._extract_text(data),
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
            modelo=model_id,
            raw=data,
        )

    def get_models(self) -> list[str]:
        response = self._request(
            "GET", f"{self.base_url}/models", headers=self._headers()
        )
        data = response.json()
        return [
            item["id"] for item in data.get("data", []) if item.get("id")
        ]

    def validate_connection(self) -> bool:
        try:
            self.get_models()
        except (ErrorProveedor, httpx.HTTPError, ValueError):
            return False
        return True

    def get_usage(self, response: Mapping[str, Any]) -> dict[str, int]:
        usage = response.get("usage") or {}
        return {
            "tokens_in": int(usage.get("prompt_tokens", 0)),
            "tokens_out": int(usage.get("completion_tokens", 0)),
        }

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _extract_text(data: Mapping[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ErrorProveedor("openrouter: respuesta sin contenido") from exc
        return content or ""
