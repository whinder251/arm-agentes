import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Agente, Habilidad, ModeloLLM, Proveedor


@pytest.mark.django_db
class TestPanelAgente(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.crear_habilidad_url = reverse("crear_habilidad")
        self.crear_agente_url = reverse("crear_agente")

    def test_usuario_no_autenticado_redirige(self):
        response = self.client.get(self.crear_agente_url)
        assert response.status_code == 302

    def test_formulario_agente_se_renderiza(self):
        self.client.login(username="testuser", password="testpass123")
        Habilidad.objects.create(
            nombre="Reescritura",
            slug="reescritura",
            plantilla_prompt="Reescribe el texto.",
        )
        response = self.client.get(self.crear_agente_url)
        assert response.status_code == 200
        assert "Reescritura" in response.content.decode()

    def test_crear_habilidad_exitoso(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.crear_habilidad_url, {
            "nombre": "Reescritura",
            "slug": "reescritura",
            "plantilla_prompt": "Reescribe el texto sin inventar datos.",
            "esquema_salida": '{"texto": "string"}',
        })
        assert response.status_code == 302
        assert Habilidad.objects.filter(slug="reescritura").exists()

    def test_crear_agente_exitoso(self):
        self.client.login(username="testuser", password="testpass123")
        proveedor = Proveedor.objects.create(
            nombre="gemini",
            api_key="fake",
            base_url="http://test.invalid",
        )
        modelo = ModeloLLM.objects.create(
            proveedor=proveedor,
            model_id="gemini-1.5-flash",
            prioridad=10,
            activo=True,
        )
        reescritura = Habilidad.objects.create(
            nombre="Reescritura",
            slug="reescritura",
            plantilla_prompt="Reescribe el texto.",
        )
        seo = Habilidad.objects.create(
            nombre="SEO",
            slug="seo",
            plantilla_prompt="Revisa el SEO.",
        )
        response = self.client.post(self.crear_agente_url, {
            "nombre": "Redactor",
            "rol": "Eres redactor SEO.",
            "temperatura": "0.7",
            "modelo": modelo.id,
            "habilidades": [str(reescritura.id), str(seo.id)],
        })
        assert response.status_code == 302
        agente = Agente.objects.get(nombre="Redactor")
        assert agente.modelo_id == modelo.id
        assert set(agente.habilidades.values_list("id", flat=True)) == {
            reescritura.id,
            seo.id,
        }
