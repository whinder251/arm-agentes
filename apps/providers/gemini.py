"""Adaptador para la API de Google Gemini."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from apps.providers.base import (
    BaseProveedor,
    ErrorProveedor,
    Messages,
    RespuestaChat,
)


class GeminiProvider(BaseProveedor):
    """Proveedor Gemini sobre la API generateContent."""

    nombre = "gemini"
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

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
        response = self._request(
            "POST",
            f"{self.base_url}/models/{model_id}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json=self._payload(messages, config or {}),
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
            "GET",
            f"{self.base_url}/models",
            headers={"x-goog-api-key": self.api_key},
        )
        data = response.json()
        return [
            item["name"].removeprefix("models/")
            for item in data.get("models", [])
            if item.get("name")
        ]

    def validate_connection(self) -> bool:
        try:
            self.get_models()
        except (ErrorProveedor, httpx.HTTPError, ValueError):
            return False
        return True

    def get_usage(self, response: Mapping[str, Any]) -> dict[str, int]:
        usage = response.get("usageMetadata") or {}
        return {
            "tokens_in": int(usage.get("promptTokenCount", 0)),
            "tokens_out": int(usage.get("candidatesTokenCount", 0)),
        }

    @staticmethod
    def _payload(
        messages: Messages, config: Mapping[str, Any]
    ) -> dict[str, Any]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            text = message.get("content", "")
            if role == "system":
                system_parts.append(text)
                continue
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}],
                }
            )
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }
        generation: dict[str, Any] = {}
        if "temperature" in config:
            generation["temperature"] = config["temperature"]
        if "max_tokens" in config:
            generation["maxOutputTokens"] = config["max_tokens"]
        if generation:
            payload["generationConfig"] = generation
        return payload

    @staticmethod
    def _extract_text(data: Mapping[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ErrorProveedor("gemini: respuesta sin contenido") from exc
        return "".join(part.get("text", "") for part in parts)
