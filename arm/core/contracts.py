"""Contratos Pydantic v2 para el Tool Gateway de ARM (núcleo independiente, sin Django)."""

from typing import Any
from pydantic import BaseModel, Field, ValidationError


class ToolSpec(BaseModel):
    """Especificación de una herramienta registrada en el Gateway."""

    slug: str
    nombre: str
    descripcion: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    requiere_credencial: bool = False
    efecto_externo: bool = False


class ToolExecutionRequest(BaseModel):
    """Petición de ejecución de una herramienta."""

    slug: str
    params: dict = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    """Resultado de la ejecución de una herramienta."""

    success: bool
    data: Any = None
    error: str | None = None
