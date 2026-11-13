import re

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Agente, Habilidad, ModeloLLM, Proveedor


@pytest.mark.django_db
class TestPanelListaHabilidades(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.habilidad = Habilidad.objects.create(
            nombre="Reescritura",
            slug="reescritura",
            plantilla_prompt="Reescribe el texto sin inventar datos.",
        )
        self.lista_url = reverse("lista_habilidades")
        self.editar_url = reverse("editar_habilidad", args=[self.habilidad.pk])
        self.eliminar_url = reverse("eliminar_habilidad", args=[self.habilidad.pk])

    def test_lista_requiere_login(self):
        response = self.client.get(self.lista_url)
        assert response.status_code == 302

    def test_lista_muestra_habilidades(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.lista_url)
        assert response.status_code == 200
        contenido = response.content.decode()
        assert "Reescritura" in contenido
        assert "reescritura" in contenido
        assert "Editar" in contenido
        assert "Eliminar" in contenido

    def test_formulario_edicion_carga(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.editar_url)
        assert response.status_code == 200
        contenido = response.content.decode()
        assert 'value="Reescritura"' in contenido
        assert "Guardar cambios" in contenido

    def test_editar_habilidad_actualiza(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.editar_url, {
            "nombre": "Reescritura editorial",
            "slug": "reescritura-editorial",
            "plantilla_prompt": "Reescribe el texto con cuidado.",
            "esquema_salida": '{"texto": "string"}',
        })
        assert response.status_code == 302
        assert response.url == self.lista_url
        self.habilidad.refresh_from_db()
        assert self.habilidad.nombre == "Reescritura editorial"
        assert self.habilidad.slug == "reescritura-editorial"

    def test_eliminar_por_post_borra(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.eliminar_url)
        assert response.status_code == 302
        assert response.url == self.lista_url
        assert not Habilidad.objects.filter(pk=self.habilidad.pk).exists()

    def test_eliminar_por_get_no_borra(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.eliminar_url)
        assert response.status_code == 405
        assert Habilidad.objects.filter(pk=self.habilidad.pk).exists()

    def test_eliminar_requiere_login(self):
        response = self.client.post(self.eliminar_url)
        assert response.status_code == 302
        assert Habilidad.objects.filter(pk=self.habilidad.pk).exists()


@pytest.mark.django_db
class TestPanelListaAgentes(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")
        self.proveedor = Proveedor.objects.create(
            nombre="Proveedor Test",
            base_url="https://example.com/api",
            api_key="clave-falsa",
        )
        self.modelo = ModeloLLM.objects.create(
            proveedor=self.proveedor,
            model_id="modelo-1",
            prioridad=10,
        )
        self.habilidad_uno = Habilidad.objects.create(
            nombre="Reescritura",
            slug="reescritura",
            plantilla_prompt="Reescribe el texto sin inventar datos.",
        )
        self.habilidad_dos = Habilidad.objects.create(
            nombre="SEO",
            slug="seo",
            plantilla_prompt="Redacta un título y una meta.",
        )
        self.agente = Agente.objects.create(
            nombre="Agente Test",
            rol="Eres un asistente editorial.",
            temperatura=0.7,
            modelo=self.modelo,
        )
        self.agente.habilidades.set([self.habilidad_uno])
        self.lista_url = reverse("lista_agentes")
        self.editar_url = reverse("editar_agente", args=[self.agente.pk])
        self.eliminar_url = reverse("eliminar_agente", args=[self.agente.pk])

    def test_lista_requiere_login(self):
        response = self.client.get(self.lista_url)
        assert response.status_code == 302

    def test_lista_muestra_agentes(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.lista_url)
        assert response.status_code == 200
        contenido = response.content.decode()
        assert "Agente Test" in contenido
        assert "Proveedor Test / modelo-1" in contenido
        assert "Editar" in contenido
        assert "Eliminar" in contenido

    def test_formulario_edicion_carga(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.editar_url)
        assert response.status_code == 200
        contenido = response.content.decode()
        assert 'value="Agente Test"' in contenido
        assert "Guardar cambios" in contenido
        assert 'class="modelo-card"' in contenido
        tarjeta_modelo = contenido.split('class="modelo-card"', 1)[1].split("</label>", 1)[0]
        assert 'name="modelo"' in tarjeta_modelo
        assert "checked" in tarjeta_modelo
        assert re.search(
            r'value="%s"\s+checked' % self.habilidad_uno.pk, contenido
        )

    def test_editar_agente_actualiza_y_sincroniza_habilidades(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.editar_url, {
            "nombre": "Agente Editorial",
            "rol": "Eres un redactor SEO.",
            "temperatura": "0.4",
            "modelo": str(self.modelo.pk),
            "habilidades": [str(self.habilidad_dos.pk)],
        })
        assert response.status_code == 302
        assert response.url == self.lista_url
        self.agente.refresh_from_db()
        assert self.agente.nombre == "Agente Editorial"
        assert self.agente.temperatura == 0.4
        assert list(self.agente.habilidades.values_list("pk", flat=True)) == [
            self.habilidad_dos.pk
        ]

    def test_eliminar_agente_por_post_borra(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(self.eliminar_url)
        assert response.status_code == 302
        assert response.url == self.lista_url
        assert not Agente.objects.filter(pk=self.agente.pk).exists()

    def test_eliminar_agente_por_get_no_borra(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(self.eliminar_url)
        assert response.status_code == 405
        assert Agente.objects.filter(pk=self.agente.pk).exists()
