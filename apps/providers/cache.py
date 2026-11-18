"""Caché de respuestas de IA con TTL, respaldada por el modelo CacheRespuesta."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any, Mapping

from django.utils import timezone

from apps.core.models import CacheRespuesta
from apps.providers.base import Messages, RespuestaChat


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


def _clave(
    messages: Messages,
    model_id: str,
    config: Mapping[str, Any] | None = None,
) -> str:
    """Devuelve el sha256 de la petición normalizada."""
    huella = _normalizar(messages, model_id, config)
    return hashlib.sha256(huella.encode("utf-8")).hexdigest()


class CacheRespuestas:
    """Guarda respuestas por hash de (messages, model_id, config) usando ORM."""

    def get(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None = None,
    ) -> RespuestaChat | None:
        """Devuelve la respuesta guardada o None si no hay coincidencia válida."""
        clave = _clave(messages, model_id, config)
        ahora = timezone.now()
        try:
            entrada = CacheRespuesta.objects.get(clave=clave, expira__gt=ahora)
        except CacheRespuesta.DoesNotExist:
            return None
        crudo = entrada.crudo or {}
        return RespuestaChat(
            texto=entrada.texto,
            tokens_in=entrada.tokens_in,
            tokens_out=entrada.tokens_out,
            modelo=entrada.modelo,
            raw=crudo if isinstance(crudo, dict) else {},
        )

    def set(
        self,
        messages: Messages,
        model_id: str,
        config: Mapping[str, Any] | None,
        respuesta: RespuestaChat,
    ) -> str:
        """Guarda la respuesta con TTL de 30 días y devuelve la clave."""
        clave = _clave(messages, model_id, config)
        crudo = json.dumps(dict(respuesta.raw), ensure_ascii=False, default=str)
        expira = timezone.now() + timedelta(days=30)
        CacheRespuesta.objects.update_or_create(
            clave=clave,
            defaults={
                "modelo": respuesta.modelo or model_id,
                "texto": respuesta.texto,
                "tokens_in": respuesta.tokens_in,
                "tokens_out": respuesta.tokens_out,
                "crudo": json.loads(crudo),
                "expira": expira,
            },
        )
        return clave


def obtener_cache(clave: str) -> dict[str, Any] | None:
    """Busca una entrada válida (no vencida) por clave.

    Retorna un dict con los datos o None si no existe o está vencida.
    """
    ahora = timezone.now()
    try:
        entrada = CacheRespuesta.objects.get(clave=clave, expira__gt=ahora)
    except CacheRespuesta.DoesNotExist:
        return None
    return {
        "clave": entrada.clave,
        "modelo": entrada.modelo,
        "texto": entrada.texto,
        "tokens_in": entrada.tokens_in,
        "tokens_out": entrada.tokens_out,
        "crudo": entrada.crudo,
        "creada": entrada.creada,
        "expira": entrada.expira,
    }


def guardar_cache(
    clave: str,
    modelo: str,
    texto: str,
    tokens_in: int,
    tokens_out: int,
    crudo: Mapping[str, Any] | None,
    ttl_dias: int = 30,
) -> CacheRespuesta:
    """Crea o actualiza una entrada de caché con TTL."""
    expira = timezone.now() + timedelta(days=ttl_dias)
    entrada, _ = CacheRespuesta.objects.update_or_create(
        clave=clave,
        defaults={
            "modelo": modelo,
            "texto": texto,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "crudo": crudo,
            "expira": expira,
        },
    )
    return entrada


def limpiar_cache_vencida() -> tuple[int, dict[str, int]]:
    """Elimina todas las entradas de caché cuyo expira ya pasó."""
    return CacheRespuesta.objects.filter(expira__lt=timezone.now()).delete()
