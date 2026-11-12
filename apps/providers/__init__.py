"""Adaptadores intercambiables de proveedores de IA."""

from apps.providers.base import (
    BaseProveedor,
    CuotaAgotada,
    ErrorProveedor,
    ErrorServidor,
    LimiteVelocidad,
    RespuestaChat,
    TimeoutProveedor,
)
from apps.providers.gemini import GeminiProvider
from apps.providers.openrouter import OpenRouterProvider

__all__ = [
    "BaseProveedor",
    "CuotaAgotada",
    "ErrorProveedor",
    "ErrorServidor",
    "GeminiProvider",
    "LimiteVelocidad",
    "OpenRouterProvider",
    "RespuestaChat",
    "TimeoutProveedor",
]
