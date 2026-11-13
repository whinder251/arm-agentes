"""Pruebas de la API REST (webhooks) sin llamadas de red reales."""

import json
from unittest.mock import patch

import pytest
from django.test import Client

from apps.core.models import Agente, Habilidad, ModeloLLM, Proveedor, Tarea


def _crear_entorno():
    proveedor = Proveedor.objects.create(
        nombre="Proveedor prueba",
        base_url="https://api.ejemplo.com",
        api_key="clave-prueba",
        limite_tokens_diario=0,
    )
    modelo = ModeloLLM.objects.create(
        proveedor=proveedor,
        model_id="modelo-prueba",
        prioridad=1,
        activo=True,
    )
    habilidad = Habilidad.objects.create(
        nombre="Reescritura",
        slug="reescritura",
        plantilla_prompt="Reescribe: {{ texto }}",
        esquema_salida={},
    )
    agente = Agente.objects.create(
        nombre="Agente prueba",
        rol="Eres un redactor.",
        temperatura=0.7,
        modelo=modelo,
    )
    agente.habilidades.add(habilidad)
    return {"proveedor": proveedor, "modelo": modelo, "habilidad": habilidad, "agente": agente}


HEADER_CORRECTO = {"HTTP_X_ARM_API_KEY": "dev-api-key-123"}
PAYLOAD = {"texto": "Texto de prueba", "habilidad_slug": "reescritura"}


@pytest.mark.django_db
def test_webhook_crear_tarea_exitoso():
    _crear_entorno()
    cliente = Client()
    with patch("apps.api.views.ejecutar_tarea") as mock_ejecutar:
        respuesta = cliente.post(
            "/api/v1/webhook/tarea/",
            data=json.dumps(PAYLOAD),
            content_type="application/json",
            **HEADER_CORRECTO,
        )
    assert respuesta.status_code == 201, respuesta.content
    datos = json.loads(respuesta.content)
    assert datos["estado"] == "cola"
    assert datos["mensaje"] == "Tarea encolada correctamente"
    assert "tarea_id" in datos
    tarea = Tarea.objects.get(pk=datos["tarea_id"])
    assert tarea.estado == Tarea.Estado.COLA
    assert tarea.habilidad.slug == "reescritura"
    mock_ejecutar.assert_called_once_with(tarea.pk)


@pytest.mark.django_db
def test_webhook_crear_tarea_sin_auth():
    _crear_entorno()
    cliente = Client()
    respuesta = cliente.post(
        "/api/v1/webhook/tarea/",
        data=json.dumps(PAYLOAD),
        content_type="application/json",
    )
    assert respuesta.status_code == 401

    respuesta_mala = cliente.post(
        "/api/v1/webhook/tarea/",
        data=json.dumps(PAYLOAD),
        content_type="application/json",
        HTTP_X_ARM_API_KEY="clave-incorrecta",
    )
    assert respuesta_mala.status_code == 401


@pytest.mark.django_db
def test_consultar_tarea_exitoso():
    entorno = _crear_entorno()
    cliente = Client()
    tarea = Tarea.objects.create(
        agente=entorno["agente"],
        habilidad=entorno["habilidad"],
        estado=Tarea.Estado.COLA,
        payload={"texto": "Texto de prueba"},
    )
    respuesta = cliente.get(
        f"/api/v1/tarea/{tarea.pk}/",
        **HEADER_CORRECTO,
    )
    assert respuesta.status_code == 200, respuesta.content
    datos = json.loads(respuesta.content)
    assert datos["tarea_id"] == tarea.pk
    assert datos["estado"] == Tarea.Estado.COLA
