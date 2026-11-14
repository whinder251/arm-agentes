"""Pruebas de IntegracionConfig, autenticación API por hash SHA-256
y destinos de publicación (C.6).

No llama APIs reales ni servicios externos.
"""

import hashlib
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.core.management import call_command

from apps.core.models import IntegracionConfig, DestinoPublicacion


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


@pytest.mark.django_db
def test_rotar_clave_arm():
    clave_anterior = "clave-anterior-123"
    IntegracionConfig.objects.create(
        nombre="ARM API",
        tipo="arm_api",
        credenciales=_hash(clave_anterior),
        activa=True,
    )
    # Un solo registro activo de tipo arm_api
    assert IntegracionConfig.objects.filter(tipo="arm_api", activa=True).count() == 1

    nuevo_token = IntegracionConfig.rotar_clave_arm()
    assert nuevo_token  # cadena no vacía
    assert nuevo_token != clave_anterior

    # El hash en BD cambió y el token nunca se guarda en texto plano
    registro = IntegracionConfig.objects.get(tipo="arm_api", activa=True)
    assert registro.credenciales == _hash(nuevo_token)
    assert registro.credenciales != nuevo_token

    # La clave anterior ya no autentica (401)
    cliente = Client()
    respuesta = cliente.get(
        "/api/v1/tarea/1/",
        HTTP_X_ARM_API_KEY=clave_anterior,
    )
    assert respuesta.status_code == 401

    # La nueva clave autentica (la tarea no existe -> 404, no 401)
    respuesta = cliente.get(
        "/api/v1/tarea/1/",
        HTTP_X_ARM_API_KEY=nuevo_token,
    )
    assert respuesta.status_code == 404

    # Se actualizó el registro existente (no se creó uno nuevo)
    assert IntegracionConfig.objects.filter(tipo="arm_api", activa=True).count() == 1


@pytest.mark.django_db
def test_destino_publicacion_guarda_credenciales_cifradas():
    destino = DestinoPublicacion.objects.create(
        nombre="Blog Principal",
        tipo="wordpress",
        url="https://blog.ejemplo.com",
        usuario="admin",
        credenciales="contraseña-secreta-123",
        activa=True,
    )
    destino.refresh_from_db()
    # Al leer desde BD se descifra y devuelve el valor real
    assert destino.credenciales == "contraseña-secreta-123"


@pytest.mark.django_db
def test_destino_publicacion_rechaza_esquema_peligroso():
    with pytest.raises(ValidationError):
        DestinoPublicacion.objects.create(
            nombre="Destino Peligroso",
            tipo="custom_api",
            url="file:///etc/passwd",
        )


@pytest.mark.django_db
def test_destino_publicacion_rechaza_loopback():
    with pytest.raises(ValidationError):
        DestinoPublicacion.objects.create(
            nombre="Loopback",
            tipo="custom_api",
            url="http://localhost:8000/",
        )
