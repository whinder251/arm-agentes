"""Pruebas del paso FASE1.6: recursos del sistema editables con restauración,
herramientas plug & play y vista de API.

Tests aislados de test_panel.py (que tiene un cuelgue preexistente de entorno).
No llaman APIs reales.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.core.models import Habilidad, FormatoSalida, Herramienta, Proveedor, ModeloLLM
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


class TestConfiguracionApi(Fase16TestCase):
    def test_configuracion_api_muestra_clave_enmascarada(self):
        """La vista muestra la URL y la clave enmascarada por defecto;
        la clave completa solo viaja en data-key para que el JS la revele al hacer clic."""
        from django.conf import settings
        api_key = getattr(settings, "ARM_API_KEY", "") or ""
        if not api_key:
            self.skipTest("ARM_API_KEY no configurada en el entorno de pruebas.")

        url = reverse("configuracion_api")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        self.assertIn("/panel/configuracion/api/", html)  # URL base presente
        # La clave enmascarada debe estar visible por defecto
        if len(api_key) > 16:
            masked = api_key[:8] + "****" + api_key[-4:]
        else:
            masked = "****"
        self.assertIn(masked, html)
        # La clave completa NO debe mostrarse como texto visible (solo en data-key para el JS)
        self.assertIn('data-key="%s"' % api_key, html)
        # El span inicial muestra la máscara, no la clave completa
        self.assertIn('>%s<' % masked, html)


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
