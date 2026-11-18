from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Herramienta


@pytest.mark.django_db
class TestAuditUI01(TestCase):
    """Contratos HTML de AUDIT-UI-01: tarjetas, labels y acciones alineadas."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass123")

    def login(self):
        self.client.login(username="testuser", password="testpass123")

    def test_agente_form_usa_card_labels_y_acciones_formulario(self):
        self.login()
        response = self.client.get(reverse("crear_agente"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert '<div class="card">' in html
        assert '<label for="id_nombre" class="label">' in html
        assert '<label for="id_rol" class="label">' in html
        assert '<label for="id_temperatura" class="label">' in html
        assert '<label class="label">Modelo</label>' in html
        assert '<label class="label">Habilidades</label>' in html
        assert '<div class="acciones-formulario">' in html
        assert "<div class=\"acciones\">" not in html

    def test_lista_herramientas_usa_contenedor_de_acciones_sin_inline(self):
        Herramienta.objects.create(
            nombre="Buscador de prueba",
            slug="buscador-prueba",
            tipo="api",
            configuracion={"endpoint": "/search"},
        )
        self.login()
        response = self.client.get(reverse("lista_herramientas"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert '<div class="tabla-acciones">' in html
        assert 'class="enlace-editar"' in html
        assert 'class="form-eliminar"' in html
        assert 'class="btn-danger-sm"' in html

        acciones = html.split('<div class="tabla-acciones">', 1)[1].split("</div>", 1)[0]
        assert "style=" not in acciones

    def test_crear_tarea_usa_card_labels_y_acciones_formulario(self):
        self.login()
        response = self.client.get(reverse("crear_tarea"))

        assert response.status_code == 200
        html = response.content.decode("utf-8")
        assert '<div class="card">' in html
        assert '<label for="texto" class="label">' in html
        assert '<label for="keyword" class="label">' in html
        assert '<label for="agente_id" class="label">' in html
        assert '<label for="instrucciones" class="label">' in html
        assert '<label for="habilidad_id" class="label">' in html
        assert '<div class="acciones-formulario">' in html
        assert '<textarea id="texto" name="texto" rows="12" class="input"' in html

    def test_css_tabla_acciones_define_gap_y_reset(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

        bloque = css.split(".tabla-acciones {", 1)[1].split("}", 1)[0]
        assert "display: flex;" in bloque
        assert "gap: 8px;" in bloque
        assert "align-items: center;" in bloque

        reset = css.split(".tabla-acciones .enlace-editar {", 1)[1].split("}", 1)[0]
        assert "margin-right: 0;" in reset
