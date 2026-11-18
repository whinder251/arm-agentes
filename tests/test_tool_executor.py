"""Tests de la infraestructura de ejecución segura de herramientas.

Ninguna llamada sale a la red; se usan mocks para HTTP y resolución DNS.
"""

from __future__ import annotations

import logging
import socket
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.core.models import Credencial, Herramienta
from apps.engine.tool_executor import (
    ToolExecutionError,
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

    def test_sanitizar_recursivo_en_headers(self):
        """Verifica que el sanitizado recorre headers anidados por nombre de clave."""
        config = {
            "headers": {
                "Authorization": "Bearer secret-token",
                "X-API-Key": "sk-live-123",
                "X-Custom-Header": "valor-normal",
                "Cookie": "session=abc",
            },
            "endpoint": "https://api.example.com",
        }
        resultado = _sanitizar_config(config)
        self.assertEqual(resultado["headers"]["Authorization"], "***")
        self.assertEqual(resultado["headers"]["X-API-Key"], "***")
        self.assertEqual(resultado["headers"]["Cookie"], "***")
        self.assertEqual(resultado["headers"]["X-Custom-Header"], "valor-normal")

    def test_sanitizar_recursivo_en_metadata(self):
        """Verifica que el sanitizado recorre metadata anidada por nombre de clave."""
        config = {
            "metadata": {
                "api_key": "sk-meta-123",
                "username": "user",
                "nested": {
                    "secret": "deep-secret",
                    "public": "valor",
                },
            },
            "endpoint": "https://api.example.com",
        }
        resultado = _sanitizar_config(config)
        self.assertEqual(resultado["metadata"]["api_key"], "***")
        self.assertEqual(resultado["metadata"]["nested"]["secret"], "***")
        self.assertEqual(resultado["metadata"]["username"], "user")
        self.assertEqual(resultado["metadata"]["nested"]["public"], "valor")


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

    @patch("socket.getaddrinfo")
    def test_ssrf_bloquea_ipv4_mapped_ipv6(self, mock_getaddrinfo):
        """Prueba que IPv4-mapped IPv6 (::ffff:127.0.0.1) se desempaqueta y bloquea."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 0, 0, 0)),
        ]
        with self.assertRaises(ValueError) as ctx:
            _validar_endpoint_seguro("http://[::ffff:127.0.0.1]")
        self.assertIn("SSRF", str(ctx.exception))
        self.assertIn("127.0.0.1", str(ctx.exception))

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

    def test_endpoint_herramienta_se_unen_con_base_url_credencial(self):
        """El endpoint de la herramienta (ruta relativa) se une con base_url de la credencial."""
        herramienta = Herramienta.objects.create(
            nombre="Herramienta Test",
            slug="herramienta-test",
            tipo="api",
            configuracion={"endpoint": "/v1/search", "timeout": 10},
            credencial=self.credencial,
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        # base_url viene de la credencial
        self.assertEqual(config["base_url"], "https://api.test.com")
        # endpoint viene de la herramienta y se une con base_url en _ejecutar_herramienta_http
        self.assertEqual(config["endpoint"], "/v1/search")
        self.assertEqual(config["secreto_desencriptado"], "sk-test-123")

    def test_endpoint_absoluto_en_herramienta_se_usa_directamente(self):
        """Si la herramienta tiene endpoint absoluto (http...), se usa tal cual (tras validar SSRF)."""
        herramienta = Herramienta.objects.create(
            nombre="Herramienta Absoluta",
            slug="herramienta-absoluta",
            tipo="api",
            configuracion={"endpoint": "https://api.otro.com/v1/data", "timeout": 10},
            credencial=self.credencial,
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        # base_url de credencial se ignora cuando endpoint es absoluto (se valida en ejecución)
        self.assertEqual(config["endpoint"], "https://api.otro.com/v1/data")
        self.assertEqual(config["secreto_desencriptado"], "sk-test-123")

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
        # endpoint de herramienta existe
        self.assertEqual(config["endpoint"], "/custom")
        # base_url viene de metadata
        self.assertEqual(config["base_url"], "https://meta.example.com")

    def test_base_url_de_herramienta_se_ignora_endpoint_no(self):
        """Verifica que base_url en herramienta.configuracion se ignora (anti cross-wiring),
        pero endpoint SÍ se toma de la herramienta (ruta legítima)."""
        credencial = Credencial.objects.create(
            nombre="Cred Test",
            slug="cred-test-2",
            tipo="api_key",
            secreto_cifrado="sk-test",
            metadata={"base_url": "https://credencial.example.com"},
        )
        herramienta = Herramienta.objects.create(
            nombre="Herramienta",
            slug="herramienta-cross-wiring",
            tipo="api",
            configuracion={
                "base_url": "https://malicioso.evil.com",  # Debe ser ignorado
                "endpoint": "/herramienta/endpoint",  # Debe usarse (ruta de la herramienta)
                "timeout": 10,
            },
            credencial=credencial,
        )
        config = _obtener_configuracion_ejecucion(herramienta)
        self.assertEqual(config["base_url"], "https://credencial.example.com")
        self.assertEqual(config["endpoint"], "/herramienta/endpoint")
        self.assertEqual(config["timeout"], 10)


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
    def test_ejecucion_http_log_sanitizado_api_key_header(self, mock_validar, mock_request):
        """Prueba que el log no filtra el secreto cuando header_scheme='api_key' con header_name personalizado."""
        self.credencial.metadata = {
            "base_url": "https://api.example.com",
            "header_scheme": "api_key",
            "header_name": "X-Custom-Key",
        }
        self.credencial.save()

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
        # Verificar que el header personalizado aparece sanitizado
        self.assertIn("X-Custom-Key", log_msg)

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_ejecucion_http_header_scheme_api_key(self, mock_validar, mock_request):
        self.credencial.metadata = {
            "base_url": "https://api.example.com",
            "header_scheme": "api_key",
            "header_name": "X-Custom-Key",
        }
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
        self.credencial.metadata = {
            "base_url": "https://api.example.com",
            "header_scheme": "basic",
            "username": "user",
        }
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
    def test_ejecucion_http_error_red_envuelto_sin_filtracion(self, mock_validar, mock_request):
        """Verifica que errores de red se envuelven en ToolExecutionError sin filtrar URL/headers."""
        mock_validar.return_value = None
        import requests as requests_lib
        mock_request.side_effect = requests_lib.ConnectionError("Connection refused")

        with self.assertRaises(ToolExecutionError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})

        # El mensaje NO debe contener la URL ni detalles sensibles
        self.assertEqual(str(ctx.exception), "Error de red al ejecutar la herramienta")
        self.assertNotIn("https://api.example.com", str(ctx.exception))
        self.assertNotIn("sk-live-abc123", str(ctx.exception))
        self.assertNotIn("Authorization", str(ctx.exception))

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

        self.assertIn("base_url", str(ctx.exception).lower())
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_allow_redirects_false_obligatorio(self, mock_validar, mock_request):
        """Verifica que allow_redirects=False se pasa obligatoriamente a requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {})

        args, kwargs = mock_request.call_args
        self.assertIn("allow_redirects", kwargs)
        self.assertFalse(kwargs["allow_redirects"])

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_invalido_none_lanza_error(self, mock_validar, mock_request):
        """Prueba que timeout=None lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "timeout": None}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Timeout inválido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_invalido_cero_lanza_error(self, mock_validar, mock_request):
        """Prueba que timeout=0 lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "timeout": 0}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Timeout inválido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_invalido_negativo_lanza_error(self, mock_validar, mock_request):
        """Prueba que timeout negativo lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "timeout": -5}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Timeout inválido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_invalido_string_lanza_error(self, mock_validar, mock_request):
        """Prueba que timeout string lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "timeout": "30"}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Timeout inválido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_timeout_fuera_de_rango_mayor_120_lanza_error(self, mock_validar, mock_request):
        """Prueba que timeout > 120 lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "timeout": 150}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Timeout inválido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_metodo_no_permitido_lanza_error(self, mock_validar, mock_request):
        """Prueba que método DELETE (no en allowlist) lanza ValueError."""
        self.herramienta.configuracion = {"endpoint": "/test", "method": "DELETE"}
        self.herramienta.save()

        mock_validar.return_value = None

        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {})
        self.assertIn("Método HTTP no permitido", str(ctx.exception))
        mock_request.assert_not_called()

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_extra_headers_no_sobrescribe_headers_protegidos(self, mock_validar, mock_request):
        """Verifica que extra_headers no puede sobrescribir Authorization, Host, etc."""
        self.herramienta.configuracion = {
            "endpoint": "/test",
            "headers": {
                "Authorization": "Bearer malicious",
                "Host": "evil.com",
                "Content-Length": "9999",
                "X-Forwarded-For": "1.2.3.4",
                "X-Custom-Header": "allowed",
            },
        }
        self.herramienta.save()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response
        mock_validar.return_value = None

        _ejecutar_herramienta_http(self.herramienta, {})

        args, kwargs = mock_request.call_args
        headers = kwargs["headers"]
        # Headers protegidos deben mantener el valor original (Bearer token)
        self.assertEqual(headers["Authorization"], "Bearer sk-live-abc123")
        # Host no debe estar en headers (requests lo maneja)
        self.assertNotIn("Host", headers)
        # Content-Length no debe ser sobrescrito
        self.assertNotIn("Content-Length", headers)
        # X-Forwarded-* no debe ser sobrescrito
        self.assertNotIn("X-Forwarded-For", headers)
        # Header personalizado permitido debe pasar
        self.assertEqual(headers["X-Custom-Header"], "allowed")

    @patch("apps.engine.tool_executor.requests.request")
    @patch("apps.engine.tool_executor._validar_endpoint_seguro")
    def test_inject_secret_in_body_colision_lanza_error(self, mock_validar, mock_request):
        """Verifica que inyección de secreto en body falla si la clave ya existe en payload."""
        self.credencial.metadata = {"base_url": "https://api.example.com"}
        self.credencial.save()
        self.herramienta.configuracion = {
            "endpoint": "/v1/endpoint",
            "inject_secret_in_body": True,
            "secret_body_key": "api_key",
        }
        self.herramienta.save()

        mock_validar.return_value = None

        # Payload ya contiene 'api_key'
        with self.assertRaises(ValueError) as ctx:
            _ejecutar_herramienta_http(self.herramienta, {"api_key": "user-provided"})
        self.assertIn("ya existe en el payload", str(ctx.exception))
        mock_request.assert_not_called()


from apps.engine.tool_executor import _resolver_placeholders


class TestResolverPlaceholders(TestCase):
    """Pruebas de resolución de placeholders {{secreto}}."""

    def test_resolver_placeholders_reemplaza_secreto(self):
        """Verifica reemplazo simple de {{secreto}} en diccionario."""
        config = {
            "headers": {
                "apikey": "{{secreto}}"
            },
            "base_url": "https://api.example.com",
        }
        resultado = _resolver_placeholders(config, "sk-real-123")
        self.assertEqual(resultado["headers"]["apikey"], "sk-real-123")
        self.assertEqual(resultado["base_url"], "https://api.example.com")

    def test_resolver_placeholders_recursivo(self):
        """Verifica reemplazo en dicts anidados y listas."""
        config = {
            "headers": {
                "Authorization": "Bearer {{secreto}}",
                "X-Custom": ["{{secreto}}", "otro-valor"],
            },
            "metadata": {
                "nested": {
                    "token": "{{secreto}}"
                }
            },
            "endpoint": "/api/v1",
        }
        resultado = _resolver_placeholders(config, "sk-live-abc")
        self.assertEqual(resultado["headers"]["Authorization"], "Bearer sk-live-abc")
        self.assertEqual(resultado["headers"]["X-Custom"], ["sk-live-abc", "otro-valor"])
        self.assertEqual(resultado["metadata"]["nested"]["token"], "sk-live-abc")
        self.assertEqual(resultado["endpoint"], "/api/v1")

    def test_resolver_placeholders_sin_placeholder(self):
        """Verifica que strings sin {{secreto}} pasan intactos."""
        config = {
            "headers": {
                "Authorization": "Bearer token-fijo",
                "X-API-Key": "sk-fijo-123",
            },
            "base_url": "https://api.example.com",
            "endpoint": "/v1/data",
        }
        resultado = _resolver_placeholders(config, "sk-real-123")
        # Nada debe cambiar porque no hay {{secreto}}
        self.assertEqual(resultado["headers"]["Authorization"], "Bearer token-fijo")
        self.assertEqual(resultado["headers"]["X-API-Key"], "sk-fijo-123")
        self.assertEqual(resultado["base_url"], "https://api.example.com")
        self.assertEqual(resultado["endpoint"], "/v1/data")

import socket