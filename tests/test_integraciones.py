"""Pruebas de IntegracionConfig y autenticación API por hash SHA-256.

No llama APIs reales ni servicios externos.
"""

import hashlib
from unittest.mock import patch

import pytest
from django.test import Client
from django.core.management import call_command

from apps.core.models import IntegracionConfig


def _hash(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


@pytest.mark.django_db
def test_comando_migrar_integraciones_crea_registro():
    with patch.dict("os.environ", {"ARM_API_KEY": "clave-prueba-123"}):
        call_command("migrar_integraciones")

    registro = IntegracionConfig.objects.get(tipo="arm_api", activa=True)
    assert registro.credenciales == _hash("clave-prueba-123")
    assert registro.credenciales != "clave-prueba-123"


@pytest.mark.django_db
def test_comando_migrar_integraciones_idempotente():
    with patch.dict("os.environ", {"ARM_API_KEY": "clave-prueba-123"}):
        call_command("migrar_integraciones")
        call_command("migrar_integraciones")

    assert IntegracionConfig.objects.filter(tipo="arm_api", activa=True).count() == 1


@pytest.mark.django_db
def test_autenticacion_api_clave_valida():
    IntegracionConfig.objects.create(
        nombre="ARM API",
        tipo="arm_api",
        credenciales=_hash("clave-valida"),
        activa=True,
    )
    cliente = Client()
    respuesta = cliente.get(
        "/api/v1/tarea/1/",
        HTTP_X_ARM_API_KEY="clave-valida",
    )
    # Autenticación pasa; la tarea no existe, por lo que responde 404 (no 401).
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_autenticacion_api_clave_invalida():
    IntegracionConfig.objects.create(
        nombre="ARM API",
        tipo="arm_api",
        credenciales=_hash("clave-valida"),
        activa=True,
    )
    cliente = Client()
    respuesta = cliente.get(
        "/api/v1/tarea/1/",
        HTTP_X_ARM_API_KEY="clave-incorrecta",
    )
    assert respuesta.status_code == 401


@pytest.mark.django_db
def test_autenticacion_api_sin_clave():
    IntegracionConfig.objects.create(
        nombre="ARM API",
        tipo="arm_api",
        credenciales=_hash("clave-valida"),
        activa=True,
    )
    cliente = Client()
    respuesta = cliente.get("/api/v1/tarea/1/")
    assert respuesta.status_code == 401


@pytest.mark.django_db
def test_credencial_no_esta_en_texto_plano():
    IntegracionConfig.objects.create(
        nombre="ARM API",
        tipo="arm_api",
        credenciales=_hash("clave-secreta"),
        activa=True,
    )
    registro = IntegracionConfig.objects.get(tipo="arm_api")
    assert registro.credenciales != "clave-secreta"
    assert registro.credenciales == _hash("clave-secreta")
