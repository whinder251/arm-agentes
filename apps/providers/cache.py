"""Caché de respuestas en SQLite, indexada por la huella de la petición."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from django.db import connection
from django.utils import timezone

from apps.providers.base import Messages, RespuestaChat

TABLA = "providers_cache_respuestas"

# La tabla se crea al vuelo para no añadir un modelo y una migración en este
# paso (el límite era de cuatro archivos). Es idempotente y no toca el esquema
# de core; si el paso 4 necesita caducar la caché por tarea, se migrará.
_CREAR_TABLA = f"""
CREATE TABLE IF NOT EXISTS {TABLA} (
    clave TEXT PRIMARY KEY,
    modelo TEXT NOT NULL,
    texto TEXT NOT NULL,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    crudo TEXT NOT NULL DEFAULT '{{}}',
    creada TEXT NOT NULL
)
"""


class CacheRespuestas:
    """Guarda respuestas por hash de (messages, model_id, config)."""

    @staticmethod
    def _normalizar(
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None,
    ) -> str:
        """Serializa la petición de forma estable para poder hashearla."""
        carga = {
            "messages": [dict(mensaje) for mensaje in messages],
            "model_id": model_id,
            "config": dict(config or {}),
        }
        return json.dumps(carga, sort_keys=True, ensure_ascii=False, default=str)

    def clave(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> str:
        """Devuelve el sha256 de la petición normalizada."""
        huella = self._normalizar(messages, model_id, config)
        return hashlib.sha256(huella.encode("utf-8")).hexdigest()

    @staticmethod
    def _asegurar_tabla() -> None:
        """Crea la tabla si aún no existe. Se llama en cada acceso."""
        with connection.cursor() as cursor:
            cursor.execute(_CREAR_TABLA)

    def get(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> RespuestaChat | None:
        """Devuelve la respuesta guardada o None si no hay coincidencia."""
        clave = self.clave(messages, model_id, config)
        self._asegurar_tabla()
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT modelo, texto, tokens_in, tokens_out, crudo "
                f"FROM {TABLA} WHERE clave = %s",
                [clave],
            )
            fila = cursor.fetchone()
        if fila is None:
            return None
        modelo, texto, tokens_in, tokens_out, crudo = fila
        try:
            raw = json.loads(crudo)
        except (TypeError, ValueError):
            raw = {}
        return RespuestaChat(
            texto=texto,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            modelo=modelo,
            raw=raw if isinstance(raw, dict) else {},
        )

    def set(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None,
        respuesta: RespuestaChat,
    ) -> str:
        """Guarda la respuesta con su marca de tiempo y devuelve la clave."""
        clave = self.clave(messages, model_id, config)
        crudo = json.dumps(dict(respuesta.raw), ensure_ascii=False, default=str)
        self._asegurar_tabla()
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {TABLA} "
                "(clave, modelo, texto, tokens_in, tokens_out, crudo, creada) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT(clave) DO UPDATE SET "
                "modelo = excluded.modelo, texto = excluded.texto, "
                "tokens_in = excluded.tokens_in, "
                "tokens_out = excluded.tokens_out, "
                "crudo = excluded.crudo, creada = excluded.creada",
                [
                    clave,
                    respuesta.modelo or model_id,
                    respuesta.texto,
                    respuesta.tokens_in,
                    respuesta.tokens_out,
                    crudo,
                    timezone.now().isoformat(),
                ],
            )
        return clave
