"""Tests del modelo CacheRespuesta con TTL. Sin llamadas a red."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import CacheRespuesta
from apps.providers.base import RespuestaChat
from apps.providers.cache import CacheRespuestas, guardar_cache, limpiar_cache_vencida, obtener_cache


@pytest.mark.django_db
def test_entrada_vencida_no_se_devuelve():
    """Una entrada con expira en el pasado retorna None."""
    ahora = timezone.now()
    CacheRespuesta.objects.create(
        clave="clave-vencida",
        modelo="gemini",
        texto="texto",
        tokens_in=1,
        tokens_out=2,
        expira=ahora - timedelta(days=1),
    )
    assert obtener_cache("clave-vencida") is None


@pytest.mark.django_db
def test_guardar_cache_actualiza_expira():
    """guardar_cache crea entrada y calcula expira correctamente."""
    clave = "clave-test"
    entrada = guardar_cache(
        clave=clave,
        modelo="gemini-2.0-flash",
        texto="hola",
        tokens_in=3,
        tokens_out=4,
        crudo={"foo": "bar"},
        ttl_dias=5,
    )
    assert entrada.expira > timezone.now()
    recuperada = obtener_cache(clave)
    assert recuperada is not None
    assert recuperada["texto"] == "hola"
    assert recuperada["modelo"] == "gemini-2.0-flash"
    assert recuperada["tokens_in"] == 3
    assert recuperada["tokens_out"] == 4


@pytest.mark.django_db
def test_limpiar_cache_vencida_elimina_entradas_pasadas():
    """limpiar_cache_vencida borra solo las entradas vencidas."""
    ahora = timezone.now()
    CacheRespuesta.objects.create(
        clave="v1", modelo="m", texto="t", expira=ahora - timedelta(days=1)
    )
    CacheRespuesta.objects.create(
        clave="v2", modelo="m", texto="t", expira=ahora + timedelta(days=1)
    )
    limpiar_cache_vencida()
    assert CacheRespuesta.objects.filter(clave="v1").exists() is False
    assert CacheRespuesta.objects.filter(clave="v2").exists() is True


@pytest.mark.django_db
def test_cache_respuestas_get_y_set_orm():
    """CacheRespuestas.get/set funciona con ORM y respeta configuración."""
    cache = CacheRespuestas()
    respuesta = RespuestaChat(
        texto="hola", tokens_in=3, tokens_out=4, modelo="gemini-2.0-flash"
    )
    clave = cache.set(
        [{"role": "user", "content": "hola"}],
        "gemini-2.0-flash",
        {"temperature": 0.2},
        respuesta,
    )
    guardada = cache.get(
        [{"role": "user", "content": "hola"}],
        "gemini-2.0-flash",
        {"temperature": 0.2},
    )
    assert guardada == respuesta
    # Config distinta no coincide
    assert (
        cache.get(
            [{"role": "user", "content": "hola"}],
            "gemini-2.0-flash",
            {"temperature": 0.7},
        )
        is None
    )
    assert clave
