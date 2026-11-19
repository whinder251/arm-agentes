import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Habilidad, FormatoSalida, Herramienta, Agente


@pytest.mark.django_db
class TestEsSistemaHabilidad(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.habilidad_sistema = Habilidad.objects.create(
            nombre="Experto UI/UX ARM Flow",
            slug="experto-ui-ux-arm",
            instrucciones="Instrucciones de prueba.",
            es_sistema=True,
        )
        self.habilidad_usuario = Habilidad.objects.create(
            nombre="Habilidad usuario",
            slug="habilidad-usuario",
            instrucciones="Instrucciones de usuario.",
            es_sistema=False,
        )
        self.editar_sistema = reverse("editar_habilidad", args=[self.habilidad_sistema.pk])
        self.eliminar_sistema = reverse("eliminar_habilidad", args=[self.habilidad_sistema.pk])
        self.editar_usuario = reverse("editar_habilidad", args=[self.habilidad_usuario.pk])
        self.eliminar_usuario = reverse("eliminar_habilidad", args=[self.habilidad_usuario.pk])
        self.lista_url = reverse("lista_habilidades")

    def login(self):
        self.client.login(username="testuser", password="testpass123")

    def test_editar_habilidad_sistema_muestra_advertencia(self):
        self.login()
        response = self.client.get(self.editar_sistema)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("alerta-warning", html)
        self.assertIn("Restaurar valores de fábrica", html)
        self.assertIn("Estás editando un recurso del sistema", html)

    def test_eliminar_habilidad_sistema_no_borra(self):
        self.login()
        response = self.client.post(self.eliminar_sistema)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.lista_url)
        self.habilidad_sistema.refresh_from_db()
        assert self.habilidad_sistema.es_sistema is True
        assert Habilidad.objects.filter(pk=self.habilidad_sistema.pk).exists()

    def test_editar_habilidad_usuario_funciona(self):
        self.login()
        response = self.client.post(self.editar_usuario, {
            "nombre": "Habilidad usuario editada",
            "slug": "habilidad-usuario-editada",
            "instrucciones": "Nuevas instrucciones.",
        })
        self.assertEqual(response.status_code, 302)
        self.habilidad_usuario.refresh_from_db()
        assert self.habilidad_usuario.nombre == "Habilidad usuario editada"

    def test_eliminar_habilidad_usuario_borra(self):
        self.login()
        response = self.client.post(self.eliminar_usuario)
        self.assertEqual(response.status_code, 302)
        assert not Habilidad.objects.filter(pk=self.habilidad_usuario.pk).exists()


@pytest.mark.django_db
class TestCRUDFormatoSalida(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.lista_url = reverse("lista_formatos")
        self.crear_url = reverse("crear_formato")

    def login(self):
        self.client.login(username="testuser", password="testpass123")

    def test_lista_formatos_render(self):
        self.login()
        response = self.client.get(self.lista_url)
        self.assertEqual(response.status_code, 200)
        assert "Formatos de salida" in response.content.decode()

    def test_crear_formato(self):
        self.login()
        response = self.client.post(self.crear_url, {
            "nombre": "Formato prueba",
            "slug": "formato-prueba",
            "descripcion": "Desc",
            "esquema": '{"type": "object"}',
            "version": "v1",
            "permite_parcial": False,
            "plantilla_formato": "",
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 302)
        assert FormatoSalida.objects.filter(slug="formato-prueba").exists()

    def test_editar_formato_sistema_permitido_con_advertencia(self):
        formato = FormatoSalida.objects.create(
            nombre="F Sistema",
            slug="f-sistema",
            esquema={},
            es_sistema=True,
        )
        self.login()
        editar_url = reverse("editar_formato", args=[formato.pk])
        response = self.client.get(editar_url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("alerta-warning", html)
        self.assertIn("Restaurar valores de fábrica", html)
        self.assertIn("Estás editando un recurso del sistema", html)
        # Ya no hay bloqueo: la vista renderiza el formulario en lugar de redirectar


@pytest.mark.django_db
class TestCRUDHerramienta(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.lista_url = reverse("lista_herramientas")
        self.crear_url = reverse("crear_herramienta")

    def login(self):
        self.client.login(username="testuser", password="testpass123")

    def test_lista_herramientas_render(self):
        self.login()
        response = self.client.get(self.lista_url)
        self.assertEqual(response.status_code, 200)
        assert "Herramientas" in response.content.decode()

    def test_crear_herramienta(self):
        self.login()
        # Sin ?tipo= la vista renderiza el catálogo (200) en lugar de crear.
        response = self.client.post(self.crear_url, {
            "nombre": "Herramienta prueba",
            "slug": "herramienta-prueba",
            "tipo": "api",
            "descripcion": "Desc",
            "configuracion": '{"clave": "valor"}',
            "es_sistema": False,
        })
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        assert "nodo-grid" in html
        assert "Herramientas" in html or "HTTP Request" in html
        # No se creó herramienta porque la vista entró al catálogo sin tipo.
        assert not Herramienta.objects.filter(slug="herramienta-prueba").exists()


@pytest.mark.django_db
class TestRecursosSistema(TestCase):
    def test_recursos_sistema_existen(self):
        # Los recursos del sistema se crean al ejecutar seed_demo; aqui los
        # creamos directamente para validar el modelo y sus relaciones.
        formato = FormatoSalida.objects.create(
            slug="componente-ui-arm",
            nombre="Componente UI Estructurado",
            esquema={
                "type": "object",
                "properties": {
                    "nombre_componente": {"type": "string"},
                    "tag_raiz": {"type": "string"},
                    "clases_arm_flow": {"type": "string"},
                    "estructura_html": {"type": "string"},
                },
                "required": ["nombre_componente", "tag_raiz", "clases_arm_flow", "estructura_html"],
            },
            es_sistema=True,
        )
        habilidad = Habilidad.objects.create(
            slug="experto-ui-ux-arm",
            nombre="Experto UI/UX ARM Flow",
            instrucciones="Instrucciones UI/UX.",
            es_sistema=True,
        )
        agente = Agente.objects.create(nombre="UI/UX", formato_salida=formato)
        agente.habilidades.add(habilidad)

        f = FormatoSalida.objects.filter(slug="componente-ui-arm").first()
        h = Habilidad.objects.filter(slug="experto-ui-ux-arm").first()
        a = Agente.objects.filter(nombre="UI/UX").first()
        self.assertIsNotNone(f)
        self.assertTrue(f.es_sistema)
        self.assertIsNotNone(h)
        self.assertTrue(h.es_sistema)
        self.assertIsNotNone(a)
        self.assertIn(h, a.habilidades.all())
        self.assertEqual(a.formato_salida, f)
