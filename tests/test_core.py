from django.test import TestCase

from apps.core.models import Habilidad, Proveedor


class TestCamposPaso15a(TestCase):
    def test_proveedor_limite_tokens_diario_default_0(self):
        p = Proveedor.objects.create(
            nombre="Proveedor prueba", base_url="https://ejemplo.com"
        )
        self.assertEqual(p.limite_tokens_diario, 0)

    def test_habilidad_modo_ejecucion_default_auto(self):
        h = Habilidad.objects.create(
            nombre="Habilidad prueba",
            slug="habilidad-prueba",
            plantilla_prompt="Prompt de prueba",
        )
        self.assertEqual(h.modo_ejecucion, "auto")
