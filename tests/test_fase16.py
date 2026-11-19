"""Pruebas del paso FASE1.6 y C.2/C.5-B: recursos del sistema editables con restauración,
herramientas plug & play, credenciales centralizadas, gestión de ARM API Key y UI n8n.

Tests aislados de test_panel.py (que tiene un cuelgue preexistente de entorno).
No llaman APIs reales.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.management import call_command
import unittest.mock
import json
import socket

from apps.core.models import Habilidad, FormatoSalida, Herramienta, Proveedor, ModeloLLM, Credencial
from apps.core import defaults


class Fase16TestCase(TestCase):
    """Base con usuario autenticado y cliente."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="tester", password="test-pass-123"
        )
        self.client.login(username="tester", password="test-pass-123")

    def _crear_proveedor_y_modelo(self):
        proveedor = Proveedor.objects.create(
            nombre="Proveedor Test",
            base_url="https://ejemplo.com",
            api_key="test-api-key-12345",
        )
        modelo = ModeloLLM.objects.create(
            proveedor=proveedor, model_id="modelo-test", prioridad=1
        )
        return proveedor, modelo


class TestEditarHabilidadSistema(Fase16TestCase):
    def test_editar_habilidad_sistema_muestra_advertencia(self):
        """Editar una habilidad de sistema no redirige; muestra advertencia y botón restaurar."""
        habilidad = Habilidad.objects.create(
            slug="experto-ui-ux-arm",
            nombre="Experto UI/UX ARM Flow",
            instrucciones="Instrucciones modificadas para la prueba.",
            modo_ejecucion="auto",
            es_sistema=True,
        )
        url = reverse("editar_habilidad", args=[habilidad.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("alerta-warning", html)
        self.assertIn("Restaurar valores de fábrica", html)
        self.assertIn("Estás editando un recurso del sistema", html)


class TestRestaurarHabilidad(Fase16TestCase):
    def test_restaurar_habilidad_revierte_default(self):
        """POST a restaurar devuelve la habilidad a sus valores de fábrica."""
        default = defaults.HABILIDADES_SISTEMA["experto-ui-ux-arm"]
        habilidad = Habilidad.objects.create(
            slug="experto-ui-ux-arm",
            nombre="Nombre modificado",
            instrucciones="Instrucciones modificadas para la prueba.",
            modo_ejecucion="manual",
            es_sistema=True,
        )
        url = reverse("restaurar_habilidad", args=[habilidad.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        habilidad.refresh_from_db()
        self.assertEqual(habilidad.nombre, default["nombre"])
        self.assertEqual(habilidad.instrucciones, default["instrucciones"])
        self.assertEqual(habilidad.modo_ejecucion, default["modo_ejecucion"])

    def test_restaurar_es_post(self):
        """GET a restaurar retorna 405 (solo se permite POST)."""
        habilidad = Habilidad.objects.create(
            slug="experto-ui-ux-arm",
            nombre="Experto UI/UX ARM Flow",
            instrucciones="Instrucciones originales.",
            modo_ejecucion="auto",
            es_sistema=True,
        )
        url = reverse("restaurar_habilidad", args=[habilidad.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


class TestListaCredenciales(Fase16TestCase):
    def test_lista_credenciales_render(self):
        """La vista lista_credenciales renderiza correctamente con la ARM API Key."""
        from django.conf import settings
        api_key = getattr(settings, "ARM_API_KEY", "") or ""
        if not api_key:
            self.skipTest("ARM_API_KEY no configurada en el entorno de pruebas.")

        url = reverse("lista_credenciales")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        # Título y subtítulo
        self.assertIn("Credenciales y API", html)
        self.assertIn("Almacén centralizado de secretos", html)

        # ARM API Key del Sistema
        self.assertIn("ARM API Key del Sistema", html)
        if len(api_key) > 16:
            masked = api_key[:8] + "****" + api_key[-4:]
        else:
            masked = "****"
        self.assertIn(masked, html)
        self.assertIn('data-key="%s"' % api_key, html)
        self.assertIn('id="display-arm-key"', html)
        self.assertIn('id="btn-toggle-arm-key"', html)

        # Botón rotar
        self.assertIn("Rotar Clave", html)
        self.assertIn('btn-danger', html)

        # Tabla de credenciales
        self.assertIn("Credenciales Centralizadas", html)
        self.assertIn("Añadir credencial", html)


class TestRotarArmApiKeyDesdeCredenciales(Fase16TestCase):
    def test_rotar_arm_api_key_requiere_autenticacion(self):
        """Sin login, POST a rotar redirige a login."""
        self.client.logout()
        url = reverse("lista_credenciales")
        response = self.client.post(url, {"rotar_arm_api_key": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    @unittest.mock.patch("apps.panel.views.set_key")
    @unittest.mock.patch(
        "apps.panel.views.secrets.token_urlsafe", return_value="tok-urlsafe-32"
    )
    def test_rotar_arm_api_key_genera_clave_y_redirige(self, mock_token, mock_set_key):
        """POST rota la ARM API Key, llama a set_key y redirige con mensaje de éxito."""
        url = reverse("lista_credenciales")
        response = self.client.post(url, {"rotar_arm_api_key": "1"}, follow=True)
        self.assertEqual(response.status_code, 200)
        mock_set_key.assert_called_once()
        args, _ = mock_set_key.call_args
        self.assertEqual(args[1], "ARM_API_KEY")
        self.assertTrue(str(args[2]).startswith("arm_"))
        self.assertRedirects(response, reverse("lista_credenciales"))
        mensajes = [str(m) for m in response.context["messages"]]
        self.assertTrue(
            any("ARM API Key renovada" in m for m in mensajes),
            f"No se encontró mensaje de éxito en: {mensajes}",
        )

    def test_sidebar_tiene_unico_enlace_credenciales_y_api(self):
        """El sidebar tiene un único enlace 'Credenciales y API'."""
        url = reverse("lista_credenciales")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        # Verifica que el enlace activo esté presente
        self.assertIn('href="%s"' % reverse("lista_credenciales"), html)
        self.assertIn("Credenciales y API", html)
        # No debe haber enlaces duplicados antiguos
        self.assertNotIn("configuracion_api", html)
        self.assertNotIn("rotar_api_key", html)


class TestSeedHerramientasSistema(Fase16TestCase):
    def test_seed_crea_4_herramientas_sistema(self):
        """seed_demo crea las 4 herramientas del sistema con es_sistema=True."""
        self._crear_proveedor_y_modelo()
        call_command("seed_demo")
        slugs_esperados = {
            "tavily-search",
            "wordpress-connector",
            "google-sheets",
            "supabase-query",
        }
        herramientas = Herramienta.objects.filter(
            slug__in=slugs_esperados, es_sistema=True
        )
        self.assertEqual(herramientas.count(), 4)
        for herramienta in herramientas:
            datos = defaults.HERRAMIENTAS_SISTEMA[herramienta.slug]
            self.assertEqual(herramienta.nombre, datos["nombre"])
            self.assertEqual(herramienta.tipo, datos["tipo"])
            self.assertEqual(herramienta.configuracion, datos["configuracion"])


class TestCredencialCRUD(Fase16TestCase):
    def test_crear_credencial(self):
        """Crear una credencial funciona correctamente."""
        url = reverse("crear_credencial")
        response = self.client.post(url, {
            "nombre": "Credencial Test",
            "slug": "credencial-test",
            "tipo": "api_key",
            "secreto_cifrado": "sk-test-1234567890",
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 302)
        credencial = Credencial.objects.get(slug="credencial-test")
        self.assertEqual(credencial.nombre, "Credencial Test")
        self.assertEqual(credencial.tipo, "api_key")

    def test_editar_credencial_sistema_muestra_advertencia(self):
        """Editar credencial de sistema muestra advertencia pero permite editar."""
        credencial = Credencial.objects.create(
            slug="credencial-sistema-test",
            nombre="Credencial Sistema",
            tipo="api_key",
            secreto_cifrado="sk-original",
            es_sistema=True,
        )
        url = reverse("editar_credencial", args=[credencial.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("alerta-warning", html)
        self.assertIn("Estás editando un recurso del sistema", html)
        # No hay botón de restaurar para credenciales (no tienen defaults)
        self.assertNotIn("Restaurar valores de fábrica", html)

    def test_eliminar_credencial_sistema_bloqueada(self):
        """Eliminar credencial de sistema está bloqueado."""
        credencial = Credencial.objects.create(
            slug="credencial-sistema-del",
            nombre="Credencial Sistema Delete",
            tipo="api_key",
            secreto_cifrado="sk-test",
            es_sistema=True,
        )
        url = reverse("eliminar_credencial", args=[credencial.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Credencial.objects.filter(pk=credencial.pk).exists())
        messages = [str(m) for m in response.wsgi_request._messages] if hasattr(response, 'wsgi_request') else []
        # Verificar que no se borró
        self.assertTrue(Credencial.objects.filter(pk=credencial.pk).exists())

    def test_eliminar_credencial_usuario_funciona(self):
        """Eliminar credencial de usuario funciona."""
        credencial = Credencial.objects.create(
            slug="credencial-usuario-del",
            nombre="Credencial Usuario Delete",
            tipo="api_key",
            secreto_cifrado="sk-test",
            es_sistema=False,
        )
        url = reverse("eliminar_credencial", args=[credencial.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Credencial.objects.filter(pk=credencial.pk).exists())


class TestCredencialEditarAPIKey(Fase16TestCase):
    """Pruebas para la nueva convención: campo vacío = conservar secreto."""

    def test_editar_credencial_dejar_vacio_conserva_secreto(self):
        """Editar solo el nombre dejando el campo API Key vacío conserva el secreto original."""
        credencial = Credencial.objects.create(
            slug="credencial-test-conserva",
            nombre="Credencial Test",
            tipo="api_key",
            secreto_cifrado="sk-original-secreto-1234",
            es_sistema=False,
        )
        url = reverse("editar_credencial", args=[credencial.pk])
        response = self.client.post(url, {
            "nombre": "Credencial Editada",
            "slug": "credencial-test-conserva",
            "tipo": "api_key",
            "secreto_cifrado": "",  # vacío = conservar
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 302)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-original-secreto-1234")

    def test_editar_credencial_escribir_nueva_clave_actualiza(self):
        """Escribir una nueva clave en el campo actualiza el secreto."""
        credencial = Credencial.objects.create(
            slug="credencial-test-actualiza",
            nombre="Credencial Test",
            tipo="api_key",
            secreto_cifrado="sk-original-secreto-1234",
            es_sistema=False,
        )
        url = reverse("editar_credencial", args=[credencial.pk])
        response = self.client.post(url, {
            "nombre": "Credencial Editada",
            "slug": "credencial-test-actualiza",
            "tipo": "api_key",
            "secreto_cifrado": "sk-nueva-clave-5678",
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 302)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-nueva-clave-5678")

    def test_editar_credencial_placeholder_enmascarado_conserva(self):
        """Dejar el placeholder enmascarado (****1234) conserva el secreto original."""
        credencial = Credencial.objects.create(
            slug="credencial-test-placeholder",
            nombre="Credencial Test",
            tipo="api_key",
            secreto_cifrado="sk-original-secreto-1234",
            es_sistema=False,
        )
        url = reverse("editar_credencial", args=[credencial.pk])
        # El formulario inicializa con el placeholder enmascarado
        response = self.client.post(url, {
            "nombre": "Credencial Editada",
            "slug": "credencial-test-placeholder",
            "tipo": "api_key",
            "secreto_cifrado": "****1234",  # placeholder enmascarado
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 302)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-original-secreto-1234")


class TestN8NUI(Fase16TestCase):
    """Pruebas para la UI estilo n8n de herramientas (Paso C.5-B)."""

    def test_catalogo_render(self):
        """GET a crear_herramienta sin tipo muestra el catálogo con 6 nodos."""
        url = reverse("crear_herramienta")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        # Verificar que están los 6 nombres de nodo
        self.assertIn("HTTP Request", html)
        self.assertIn("Supabase", html)
        self.assertIn("Google Sheets", html)
        self.assertIn("WordPress", html)
        self.assertIn("Tavily Search", html)
        self.assertIn("Personalizada", html)
        # Verificar que es el template de catálogo (grid)
        self.assertIn("nodo-grid", html)
        self.assertIn("nodo-card", html)

    def test_form_http_preseleccionado(self):
        """GET a crear_herramienta?tipo=supabase-query muestra formulario con campos esperados."""
        url = reverse("crear_herramienta") + "?tipo=supabase-query"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        # Verificar campos específicos de Supabase
        self.assertIn('name="endpoint"', html)
        self.assertIn('name="method"', html)
        self.assertIn('name="timeout"', html)
        # Verificar sidebar con ayuda de Supabase
        self.assertIn("La base_url vive en la credencial", html)
        # Verificar que NO está en modo avanzado por defecto
        self.assertIn('id="fieldset-estructurado"', html)
        self.assertIn('class="fieldset-estructurado"', html)

    def test_herramienta_form_simple_genera_json(self):
        """POST en modo simple crea herramienta con configuracion JSON correcta."""
        url = reverse("crear_herramienta") + "?tipo=supabase-query"
        response = self.client.post(url, {
            "nombre": "Test Supabase",
            "slug": "test-supabase",
            "tipo": "api",
            "descripcion": "Test",
            "credencial": "",
            "es_sistema": False,
            "endpoint": "posts",
            "method": "GET",
            "timeout": "30",
            "advanced_mode": False,
        })
        self.assertEqual(response.status_code, 302)  # redirect on success
        herramienta = Herramienta.objects.get(slug="test-supabase")
        self.assertEqual(herramienta.configuracion.get("endpoint"), "posts")
        self.assertEqual(herramienta.configuracion.get("method"), "GET")
        self.assertEqual(herramienta.configuracion.get("timeout"), 30)

    def test_modo_avanzado_conserva_json(self):
        """POST con advanced_mode=True guarda el JSON crudo tal cual."""
        url = reverse("crear_herramienta") + "?tipo=custom"
        custom_json = '{"custom_key": 42, "nested": {"foo": "bar"}}'
        response = self.client.post(url, {
            "nombre": "Test Custom",
            "slug": "test-custom",
            "tipo": "api",  # tipo válido del modelo
            "descripcion": "Test",
            "credencial": "",
            "es_sistema": False,
            "configuracion": custom_json,
            "advanced_mode": "on",  # checkbox value
        })
        self.assertEqual(response.status_code, 302)
        herramienta = Herramienta.objects.get(slug="test-custom")
        self.assertEqual(herramienta.configuracion, {"custom_key": 42, "nested": {"foo": "bar"}})

    def test_claves_no_mapeadas_sobreviven(self):
        """Editar herramienta existente con claves extra no mapeadas las conserva."""
        # Crear herramienta con claves extra
        herramienta = Herramienta.objects.create(
            nombre="Test Extra",
            slug="test-extra",
            tipo="api",
            descripcion="Test",
            configuracion={"params": {"x": 1}, "endpoint": "/old", "extra_field": "keepme"},
            es_sistema=False,
        )
        # Editar en modo simple cambiando solo endpoint
        url = reverse("editar_herramienta", args=[herramienta.pk])
        response = self.client.post(url, {
            "nombre": "Test Extra",
            "slug": "test-extra",
            "tipo": "api",
            "descripcion": "Test",
            "credencial": "",
            "es_sistema": False,
            "tool_type": "http_request",  # tipo que tiene endpoint, method, timeout
            "endpoint": "/new",
            "method": "POST",
            "timeout": "30",
            "advanced_mode": False,
        })
        self.assertEqual(response.status_code, 302)
        herramienta.refresh_from_db()
        # Verificar que params y extra_field sobreviven
        self.assertEqual(herramienta.configuracion.get("params"), {"x": 1})
        self.assertEqual(herramienta.configuracion.get("extra_field"), "keepme")
        # Verificar que endpoint se actualizó
        self.assertEqual(herramienta.configuracion.get("endpoint"), "/new")

    def test_sidebar_ayuda_dinamico(self):
        """GET a editar herramienta tipo supabase muestra ayuda de Supabase en sidebar."""
        herramienta = Herramienta.objects.create(
            nombre="Test Supabase Edit",
            slug="test-supabase-edit",
            tipo="api",
            descripcion="Test",
            configuracion={"endpoint": "posts", "method": "GET", "timeout": 30},
            es_sistema=False,
        )
        url = reverse("editar_herramienta", args=[herramienta.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        # Verificar ayuda específica de Supabase en sidebar
        self.assertIn("La base_url vive en la credencial", html)
        self.assertIn("GRANT SELECT en el SQL Editor", html)


class TestSupabaseDiscovery(Fase16TestCase):
    """Pruebas para el descubrimiento de tablas de Supabase (Paso C.6-A)."""

    def _crear_credencial_supabase(self, tipo="api_key", base_url="https://proyecto.supabase.co/rest/v1", **kwargs):
        """Helper para crear credencial tipo Supabase."""
        return Credencial.objects.create(
            slug=kwargs.get("slug", "credencial-supabase-test"),
            nombre=kwargs.get("nombre", "Credencial Supabase Test"),
            tipo=tipo,
            secreto_cifrado=kwargs.get("secreto", "sk-test-secret-1234"),
            metadata={"base_url": base_url, "header_scheme": kwargs.get("header_scheme", "api_key")},
            es_sistema=kwargs.get("es_sistema", False),
        )

    def test_descubrir_tablas_sin_login_redirige(self):
        """GET sin autenticación redirige a login."""
        credencial = self._crear_credencial_supabase()
        self.client.logout()
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_descubrir_tablas_credencial_tipo_invalido(self):
        """Credencial tipo 'json' devuelve 400 con error claro."""
        credencial = Credencial.objects.create(
            slug="credencial-json",
            nombre="Credencial JSON",
            tipo="json",
            secreto_cifrado="{}",
            metadata={"base_url": "https://api.ejemplo.com"},
            es_sistema=False,
        )
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("Tipo de credencial no soportado", data["error"])

    def test_descubrir_tablas_sin_base_url(self):
        """Credencial sin base_url en metadata devuelve 400."""
        credencial = Credencial.objects.create(
            slug="credencial-sin-url",
            nombre="Credencial Sin URL",
            tipo="api_key",
            secreto_cifrado="sk-test",
            metadata={},  # sin base_url
            es_sistema=False,
        )
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("base_url", data["error"])

    @unittest.mock.patch("apps.panel.views.requests.get")
    @unittest.mock.patch("socket.getaddrinfo")
    def test_descubrir_tablas_mock_supabase(self, mock_getaddrinfo, mock_get):
        """Mock de Supabase OpenAPI spec: extrae tablas válidas y filtra RPC, raíz, parámetros."""
        # Mockear resolución DNS para pasar validación SSRF (IP pública global)
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0)),
        ]
        # Crear spec simulada de Supabase
        mock_spec = {
            "paths": {
                "/core_tarea": {"get": {}},
                "/rpc/get_count": {"post": {}},
                "/": {"get": {}},
                "/auth/users": {"get": {}},
                "/posts/{id}": {"get": {}},
                "/comments": {"get": {}},
            }
        }
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_spec
        mock_get.return_value = mock_response

        credencial = self._crear_credencial_supabase()
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("tables", data)
        # Debe incluir core_tarea, auth/users, comments
        # NO debe incluir: /rpc/..., /, /posts/{id}
        self.assertEqual(data["tables"], ["auth/users", "comments", "core_tarea"])
        mock_get.assert_called_once()

    @unittest.mock.patch("apps.panel.views.requests.get")
    @unittest.mock.patch("socket.getaddrinfo")
    def test_descubrir_tablas_error_red(self, mock_getaddrinfo, mock_get):
        """Error de red (ConnectionError) devuelve 502 sin exponer secreto."""
        import requests
        # Mockear resolución DNS para pasar validación SSRF
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0)),
        ]
        mock_get.side_effect = requests.ConnectionError("DNS fallo")

        credencial = self._crear_credencial_supabase(secreto="sk-secreto-super-seguro-9999")
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertIn("error", data)
        # Verificar que el mensaje NO contiene el secreto
        self.assertNotIn("sk-secreto-super-seguro-9999", str(data))
        self.assertNotIn("secreto", str(data).lower())

    def test_descubrir_tablas_bloquea_ssrf(self):
        """Credencial con base_url en localhost/127.0.0.1 es rechazada por SSRF (400)."""
        credencial = self._crear_credencial_supabase(base_url="http://127.0.0.1:8000/rest/v1")
        url = reverse("descubrir_tablas", args=[credencial.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("SSRF", data["error"])
        # Verificar que NO se hizo la petición HTTP (mock no necesario, el validador bloquea antes)