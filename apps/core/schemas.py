"""Esquemas Pydantic v2 para validar payloads de la API REST."""

from pydantic import BaseModel, Field


class TareaCreateSchema(BaseModel):
    """Payload de entrada para crear una tarea vía webhook."""

    texto: str = Field(min_length=1)
    keyword: str | None = None
    instrucciones: str | None = None
    habilidad_slug: str
