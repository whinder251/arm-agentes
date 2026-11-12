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
from apps.providers.cache import CacheRespuestas
from apps.providers.gemini import GeminiProvider
from apps.providers.openrouter import OpenRouterProvider
from apps.providers.quota import CuotaDiaria
from apps.providers.router import Router

__all__ = [
    "BaseProveedor",
    "CacheRespuestas",
    "CuotaAgotada",
    "CuotaDiaria",
    "ErrorProveedor",
    "ErrorServidor",
    "GeminiProvider",
    "LimiteVelocidad",
    "OpenRouterProvider",
    "RespuestaChat",
    "Router",
    "TimeoutProveedor",
]
