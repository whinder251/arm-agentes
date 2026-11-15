"""Contratos Pydantic v2 para respuestas universales de proveedores de IA y API REST."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TareaCreateSchema(BaseModel):
    """Esquema de entrada para crear una tarea vía webhook REST."""

    habilidad_slug: str
    texto: str
    keyword: str | None = None
    instrucciones: str | None = None


class ErrorEstructurado(BaseModel):
    """Error devuelto por el normalizador cuando una respuesta no cumple el esquema."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ResultadoAgente(BaseModel):
    """Resultado normalizado de una tarea de agente, independiente del proveedor."""

    success: bool
    status: Literal["completed", "partial", "failed"]
    data: Any | None = None
    error: ErrorEstructurado | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EsquemaHabilidad(BaseModel):
    """Descripción del esquema de salida de una habilidad."""

    tipo: str
    campos: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
