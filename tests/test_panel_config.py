import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Proveedor, ModeloLLM


@pytest.mark.django_db
class TestPanelConfig(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.config_url = reverse('configuracion')
        self.crear_proveedor_url = reverse('crear_proveedor')
        self.crear_modelo_url = reverse('crear_modelo')

    def test_usuario_no_autenticado_redirige(self):
        response = self.client.get(self.config_url)
        assert response.status_code == 302

    def test_crear_proveedor_exitoso(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(self.crear_proveedor_url, {
            'nombre': 'OpenAI',
            'base_url': 'https://api.openai.com/v1',
            'api_key': 'sk-test123',
            'rpm': 60,
            'limite_diario': 1000,
        })
        assert response.status_code == 302
        assert Proveedor.objects.filter(nombre='OpenAI').exists()

    def test_crear_modelo_exitoso(self):
        self.client.login(username='testuser', password='testpass123')
        proveedor = Proveedor.objects.create(
            nombre='gemini',
            api_key='fake',
            base_url='http://test.invalid',
        )
        response = self.client.post(self.crear_modelo_url, {
            'proveedor': proveedor.id,
            'model_id': 'gemini-1.5-flash',
            'prioridad': 10,
            'json_nativo': 'false',
            'activo': 'on',
        })
        assert response.status_code == 302
        assert ModeloLLM.objects.filter(
            model_id='gemini-1.5-flash', proveedor=proveedor
        ).exists()
