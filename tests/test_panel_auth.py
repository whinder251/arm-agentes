import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase

@pytest.mark.django_db
class TestPanelAuth(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.login_url = reverse('login_panel')
        self.lista_url = reverse('lista_tareas')
        self.logout_url = reverse('logout_panel')

    def test_login_redirige_sin_credenciales(self):
        response = self.client.post(self.login_url, {'username': '', 'password': ''})
        assert response.status_code == 200
        assert 'Credenciales inválidas' in response.content.decode('utf-8')

    def test_login_correcto(self):
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'testpass123'
        })
        assert response.status_code == 302
        assert response.url == self.lista_url
        
        # Verificar que la sesión quedó autenticada
        response_lista = self.client.get(self.lista_url)
        assert response_lista.status_code == 200

    def test_logout(self):
        # Primero nos logueamos
        self.client.login(username='testuser', password='testpass123')
        
        # Luego hacemos logout
        response = self.client.post(self.logout_url)
        assert response.status_code == 302
        assert response.url == self.login_url
        
        # Verificar que la sesión quedó anónima
        response_lista = self.client.get(self.lista_url)
        assert response_lista.status_code == 302  # Debería redirigir al login