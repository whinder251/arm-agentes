"""Tests de la infraestructura de ejecución segura de herramientas.

Ninguna llamada sale a la red; se usan mocks para HTTP y resolución DNS.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.core.models import Credencial, Herramienta
from apps.engine.tool_executor import (
    _ejecutar_herramienta_http,
    _obtener_configuracion_ejecucion,
    _sanitizar_config,
    _validar_endpoint_seguro,
)


# Fixture para caplog compatible con TestCase
@pytest.fixture
def caplog(caplog):
    return caplog


class TestSanitizarConfig(TestCase):
    """Pruebas de sanitizado de configuración para logs."""

    def test_sanitizar_oculta_claves_sensibles(self):
        config = {
            "api_key": "sk-real-123",
            "endpoint": "https://api.example.com",
            "secreto": "secret-value",
            "password": "pwd123",
            "token": "Bearer xxx",
            "secreto_desencriptado": "plain-secret",
            "credentials_json": '{"key": "val"}',
            "app_password": "app-pwd",
            "timeout": 30,
            "otro_campo": "valor",
        }
        resultado = _sanitizar_config(config)
        self.assertEqual(resultado["api_key"], "***")
        self.assertEqual(resultado["secreto"], "***")
        self.assertEqual(resultado["password"], "***")
        self.assertEqual(resultado["token"], "***")
        self.assertEqual(resultado["secreto_desencriptado"], "***")
        self.assertEqual(resultado["credentials_json"], "***")
        self.assertEqual(resultado["app_password"], "***")
        self.assertEqual(resultado["endpoint"], "https://api.example.com")
        self.assertEqual(resultado["timeout"], 30)
        self.assertEqual(resultado["otro_campo"], "valor")

    def test_sanitizar_case_insensitive(self):
        config = {"API_KEY": "real", "Api_Key": "real2", "SeCrEtO": "real3"}
        resultado = _sanitizar_config(config)
        self.assertEqual(resultado["API_KEY"], "***")
        self.assertEqual(resultado["Api_Key"], "***")
        self.assertEqual(resultado["SeCrEtO"], "***")

    def test_sanitizar_no_modifica_original(self):
        original = {"api_key": "real", "endpoint": "url"}
        _sanitizar_config(original)
        self.assertEqual(original["api_key"], "real")


class TestValidarEndpointSeguro(TestCase):
    """Pruebas de validación SSRF."""

    @patch("socket.getaddrinfo")
    def test_ssrf_permite_host_publico(self, mock_getaddrinfo):
        # Mock para devolver IP pública (Google DNS)
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        ]
        # No debe lanzar excepción
        _validar_endpoint_seguro("https://api.example.com")

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_localhost(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://localhost:8000")
        self.assertIn("SSRF", str(ctx.exception))
        self.assertIn("127.0.0.1", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_169_254(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://169.254.169.254")
        self.assertIn("SSRF", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_rango_privado_10(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://interno.empresa.local")
        self.assertIn("SSRF", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_rango_privado_172(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.16.0.10", 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://172.16.0.10")
        self.assertIn("SSRF", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_rango_privado_192(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://192.168.1.50")
        self.assertIn("SSRF", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_loopback_ipv6(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://[::1]")
        self.assertIn("SSRF", str(ctx.exception))

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_unique_local_ipv6(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fc00::1", 0, 0, 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://[fc00::1]")
        self.assertIn("SSRF", str(ctx.exception))

    def test_endpoint_vacio_lanza_error(self):
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("")
        self.assertIn("vacío", str(ctx.exception).lower())

    def test_url_sin_hostname_lanza_error(self):
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http:///path")
        self.assertIn("hostname", str(ctx.exception).lower())


class TestObtenerConfiguracionEjecucion(TestCase):
    """Pruebas de fusión de configuración con credencial."""

    def setUp(self):
        self.credencial = Credencial.objects.create(
            nombre="Credencial Test",
            slug="credencial-test",
            tipo="api_key",
            secreto_cifrado="sk-test-123",
            metadata={"base_url": "https://api.test.com", "header_scheme": "bearer"},
        )

    def test_fusion_metadata_config_secreto(self):
        herramienta = Herramienta.objects.create(
            nombre="Herramienta Test",
            slug="herramienta-test",
            tipo="api",
            configuracion={"endpoint": "/v1/data", "timeout": 10},
            credencial=self.credencial,
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        self.assertEqual(config["base_url"], "https://api.test.com")
        self.assertEqual(config["header_scheme"], "bearer")
        self.assertEqual(config["endpoint"], "/v1/data")
        self.assertEqual(config["timeout"], 10)
        self.assertEqual(config["secreto_desencriptado"], "sk-test-123")

    def test_ejecucion_sin_credencial_devuelve_config_original(self):
        herramienta = Herramienta.objects.create(
            nombre="Herramienta Sin Cred",
            slug="herramienta-sin-cred",
            tipo="api",
            configuracion={"endpoint": "/v1/data", "timeout": 15},
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        self.assertEqual(config["endpoint"], "/v1/data")
        self.assertEqual(config["timeout"], 15)
        self.assertNotIn("secreto_desencriptado", config)

    def test_credencial_vacia_lanza_error(self):
        credencial_vacia = Credencial.objects.create(
            nombre="Credencial Vacía",
            slug="credencial-vacia",
            tipo="api_key",
            secreto_cifrado="",  # Secreto vacío
            metadata={},
        )
        herramienta = Herramienta.objects.create(
            nombre="Herramienta Con Cred Vacía",
            slug="herramienta-cred-vacia",
            tipo="api",
            configuracion={"endpoint": "/v1/data"},
            credencial=credencial_vacia,
        )
        with self.assertRaises(ValueError) as ctx:
            _obtener_configuracion_ejecucion(herramienta)
        self.assertIn("secreto está vacío", str(ctx.exception))

    def test_prioridad_config_sobre_metadata(self):
        """La configuración de la herramienta tiene prioridad sobre metadata."""
        credencial = Credencial.objects.create(
            nombre="Cred Test",
            slug="cred-test",
            tipo="api_key",
            secreto_cifrado="sk-test",
            metadata={"timeout": 5, "base_url": "https://meta.example.com"},
        )
        herramienta = Herramienta.objects.create(
            nombre="Herramienta",
            slug="herramienta-prioridad",
            tipo="api",
            configuracion={"timeout": 30, "endpoint": "/custom"},
            credencial=credencial,
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        # timeout de herramienta (30) gana sobre metadata (5)
        self.assertEqual(config["timeout"], 30)
        # endpoint de herramienta existe, metadata no tiene endpoint
        self.assertEqual(config["endpoint"], "/custom")
        # base_url viene de metadata
        self.assertEqual(config["base_url"], "https://meta.example.com")


class TestEjecutarHerramientaHttp(TestCase):
    """Pruebas de ejecución HTTP con mocks."""

    def setUp(self):
        self.credencial = Credencial.objects.create(
            nombre="Credencial HTTP",
            slug="credencial-http",
            tipo="api_key",
            secreto_cifrado="sk-live-abc123",
            metadata={
                "base_url": "https://api.example.com",
                "header_scheme": "bearer",
            },
        )
        self.herramienta = Herramienta.objects.create(
            nombre="Herramienta HTTP",
            slug="herramienta-http",
            tipo="api",
            configuracion={"endpoint": "/v1/endpoint", "timeout": 20},
            credencial=self.credencial,
        )

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_mock_inyecta_secreto(self, mock_validar, mock_request):
        # Configurar mock de respuesta
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "data": "result"}
        mock_request.return_value = mock_response

        # Mock validar para que no falle SSRF
        mock_validar.return_value = None

        payload = {"query": "test query"}
        resultado = _ejecutar_herramienta_http(self.herramienta, payload)

        # Verificar que se llamó a requests.request con los parámetros correctos
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args

        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["url"], "https://api.example.com/v1/endpoint")
        self.assertEqual(kwargs["timeout"], 20)
        self.assertEqual(kwargs["json"], payload)

        # Verificar header de autenticación
        headers = kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer sk-live-abc123")

        # Verificar resultado
        self.assertEqual(resultado["status"], 200)
        self.assertEqual(resultado["body"], {"ok": True, "data": "result"})

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_log_sanitizado(self, mock_validar, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        # Capturar logs usando logging.Handler
        log_records = []

        class TestHandler(logging.Handler):
            def emit(self, record):
                log_records.append(record.getMessage())

        logger = logging.getLogger("apps.engine.tool_executor")
        handler = TestHandler()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            _ejecutar_herramienta_http(self.herramienta, {"test": "data"})
        finally:
            logger.removeHandler(handler)

        # Buscar el log de ejecución
        log_ejecucion = [l for l in log_records if "Ejecutando herramienta" in l]
        self.assertTrue(log_ejecucion, "No se encontró log de ejecución")
        log_msg = log_ejecucion[0]

        # El secreto NO debe aparecer en el log
        self.assertNotIn("sk-live-abc123", log_msg)
        self.assertIn("***", log_msg)

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_header_scheme_api_key(self, mock_validar, mock_request):
        self.credencial.metadata = {"base_url": "https://api.example.com", "header_scheme": "api_key", "header_name": "X-Custom-Key"}
        self.credencial.save()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {})

        args, kwargs = mock_request.call_args
        headers = kwargs["headers"]
        self.assertEqual(headers["X-Custom-Key"], "sk-live-abc123")
        self.assertNotIn("Authorization", headers)

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_header_scheme_basic(self, mock_validar, mock_request):
        self.credencial.metadata = {"base_url": "https://api.example.com", "header_scheme": "basic", "username": "user"}
        self.credencial.save()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {})

        args, kwargs = mock_request.call_args
        headers = kwargs["headers"]
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_inject_secret_in_body(self, mock_validar, mock_request):
        self.credencial.metadata = {"base_url": "https://api.example.com"}
        self.credencial.save()
        self.herramienta.configuracion = {
            "endpoint": "/v1/endpoint",
            "inject_secret_in_body": True,
            "secret_body_key": "api_token",
        }
        self.herramienta.save()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {"query": "test"})

        args, kwargs = mock_request.call_args
        json_payload = kwargs["json"]
        self.assertEqual(json_payload["api_token"], "sk-live-abc123")
        self.assertEqual(json_payload["query"], "test")

    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_ssrf_bloquea(self, mock_validar):
        mock_validar.side_effect = ValueError("Endpoint bloqueado por política SSRF: 127.0.0.1")

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})

        self.assertIn("SSRF", str(ctx.exception))

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_error_red_propagado(self, mock_validar, mock_request):
        mock_validar.return_value = None
        import requests as requests_lib
        mock_request.side_effect = requests_lib.ConnectionError("Connection refused")

        with self.assertRaises(requests_lib.ConnectionError):
            _ejecutar_herramienta_http(self.herramienta, {})

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_default_30(self, mock_validar, mock_request):
        """Si no hay timeout en config, usa default 30."""
        herramienta_sin_timeout = Herramienta.objects.create(
            nombre="Sin Timeout",
            slug="sin-timeout",
            tipo="api",
            configuracion={"endpoint": "/test"},
            credencial=self.credencial,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(herramienta_sin_timeout, {})

        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["timeout"], 30)

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_metodo_personalizado(self, mock_validar, mock_request):
        self.herramienta.configuracion = {"endpoint": "/test", "method": "GET"}
        self.herramienta.save()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {})

        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "GET")

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_herramienta_sin_endpoint_ni_base_url_lanza_error(self, mock_validar, mock_request):
        mock_validar.return_value = None
        mock_request.side_effect = AssertionError("No debería llegar a hacer la petición")

        # Credencial SIN base_url en metadata
        credencial_sin_url = Credencial.objects.create(
            nombre="Credencial Sin URL",
            slug="credencial-sin-url",
            tipo="api_key",
            secreto_cifrado="sk-test",
            metadata={},  # Sin base_url
        )
        herramienta_sin_url = Herramienta.objects.create(
            nombre="Sin URL",
            slug="sin-url",
            tipo="api",
            configuracion={"timeout": 10},  # Sin endpoint
            credencial=credencial_sin_url,
        )

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(herramienta_sin_url, {})

        self.assertIn("endpoint", str(ctx.exception).lower())
        mock_request.assert_not_called()


import socket