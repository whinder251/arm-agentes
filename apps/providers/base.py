"""Interfaz común de los adaptadores de proveedores de IA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx

Messages = Sequence[Mapping[str, str]]


class ErrorProveedor(Exception):
    """Error base de la capa de proveedores."""


class CuotaAgotada(ErrorProveedor):
    """El proveedor informa de que se agotó la cuota o el saldo."""


class LimiteVelocidad(ErrorProveedor):
    """El proveedor rechaza la petición por exceso de ritmo (HTTP 429)."""


class ErrorServidor(ErrorProveedor):
    """El proveedor responde con un error interno (HTTP 5xx)."""


class TimeoutProveedor(ErrorProveedor):
    """La petición supera el tiempo máximo configurado."""


@dataclass(frozen=True)
class RespuestaChat:
    """Respuesta normalizada, independiente del proveedor."""

    texto: str
    tokens_in: int
    tokens_out: int
    modelo: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)


class BaseProveedor(ABC):
    """Contrato que cumplen todos los proveedores."""

    nombre = "base"

    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0):
        if not api_key:
            raise ValueError("api_key es obligatoria")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BaseProveedor":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @abstractmethod
    def chat(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> RespuestaChat:
        """Envía una conversación y devuelve la respuesta normalizada."""

    @abstractmethod
    def get_models(self) -> list[str]:
        """Lista los identificadores de modelo disponibles."""

    @abstractmethod
    def validate_connection(self) -> bool:
        """Comprueba que la credencial y el endpoint responden."""

    @abstractmethod
    def get_usage(self, response: Mapping[str, Any]) -> dict[str, int]:
        """Extrae tokens de entrada y salida de una respuesta cruda."""

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Ejecuta la petición y traduce timeouts y estados HTTP."""
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutProveedor(
                f"{self.nombre}: la petición superó {self.timeout} segundos"
            ) from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise LimiteVelocidad(f"{self.nombre}: límite de velocidad alcanzado")
        if response.status_code == 402:
            raise CuotaAgotada(f"{self.nombre}: cuota o saldo agotado")
        if 500 <= response.status_code < 600:
            raise ErrorServidor(
                f"{self.nombre}: error del servidor ({response.status_code})"
            )
        response.raise_for_status()
