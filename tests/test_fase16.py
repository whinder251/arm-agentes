"""Pruebas del paso FASE1.6 y C.2: recursos del sistema editables con restauración,
herramientas plug & play, credenciales centralizadas y gestión de ARM API Key.

Tests aislados de test_panel.py (que tiene un cuelgue preexistente de entorno).
No llaman APIs reales.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.management import call_command
import unittest.mock

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
        self.assertIn("Rotar Clave del Sistema", html)
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
    """Pruebas para el patrón cambiar_api_key en CredencialForm."""

    def test_editar_credencial_sin_cambiar_api_key_conserva_secreto(self):
        """Editar solo el nombre sin marcar 'Cambiar API Key' conserva el secreto original."""
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
            "secreto_cifrado": "",  # vacío, no se marca cambiar_api_key
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
            "cambiar_api_key": False,
        })
        self.assertEqual(response.status_code, 302)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-original-secreto-1234")

    def test_editar_credencial_con_cambiar_api_key_actualiza(self):
        """Marcar 'Cambiar API Key' y escribir nueva clave actualiza el secreto."""
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
            "cambiar_api_key": True,
        })
        self.assertEqual(response.status_code, 302)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-nueva-clave-5678")

    def test_editar_credencial_marca_cambiar_sin_clave_error(self):
        """Marcar 'Cambiar API Key' pero dejar el campo vacío muestra error de validación."""
        credencial = Credencial.objects.create(
            slug="credencial-test-error",
            nombre="Credencial Test",
            tipo="api_key",
            secreto_cifrado="sk-original-secreto-1234",
            es_sistema=False,
        )
        url = reverse("editar_credencial", args=[credencial.pk])
        response = self.client.post(url, {
            "nombre": "Credencial Editada",
            "slug": "credencial-test-error",
            "tipo": "api_key",
            "secreto_cifrado": "",  # vacío
            "metadata": '{"endpoint": "https://api.ejemplo.com"}',
            "es_sistema": False,
            "cambiar_api_key": True,
        })
        self.assertEqual(response.status_code, 200)  # vuelve al formulario con error
        html = response.content.decode("utf-8")
        self.assertIn("Debes escribir la nueva API Key para cambiarla", html)
        credencial.refresh_from_db()
        self.assertEqual(credencial.secreto_cifrado, "sk-original-secreto-1234")