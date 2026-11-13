from django.db import connection
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


class TestCifradoApiKey(TestCase):
    def test_api_key_se_cifra_y_descifra(self):
        clave_original = "sk-test-1234567890abcdef"
        Proveedor.objects.create(
            nombre="Proveedor cifrado",
            base_url="https://ejemplo.com",
            api_key=clave_original,
        )
        # En BD el valor debe estar cifrado (diferente al original): se lee
        # el valor crudo de la columna para evitar que from_db_value lo descifre.
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT api_key FROM core_proveedor WHERE nombre = %s',
                ["Proveedor cifrado"],
            )
            valor_bd = cursor.fetchone()[0]
        self.assertNotEqual(valor_bd, clave_original)
        self.assertTrue(valor_bd.startswith("gAAAAA"), "Valor BD no parece un token Fernet")
        # Al acceder al modelo se obtiene el texto plano original
        self.assertEqual(
            Proveedor.objects.get(nombre="Proveedor cifrado").api_key, clave_original
        )
