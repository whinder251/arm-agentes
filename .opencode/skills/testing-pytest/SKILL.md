---
name: testing-pytest
description: Reglas para escribir pruebas con pytest y pytest-django en ARM Agentes (determinismo, mocks de APIs externas, acceso a BD, caminos feliz y de error). Úsala al crear o modificar tests en tests/, o al añadir campos a modelos que puedan romper tests existentes.
---

# Skill: Testing with Pytest & Django

## Contexto
Suite de pruebas ubicada en `tests/`. Se utiliza `pytest` y `pytest-django`.

## Reglas Estrictas
- **Determinismo**: Las pruebas deben pasar siempre, independientemente del orden de ejecución o del estado de la red.
- **Mocking de APIs Externas**: NUNCA hacer llamadas reales a `requests.get`, `DDGS` (DuckDuckGo), o APIs de IA en los tests. Usar `unittest.mock.patch` para simular respuestas.
- **Fixtures de Base de Datos**: Usar `@pytest.mark.django_db` o heredar de `TestCase` para pruebas que toquen la BD.
- **Cobertura de Flujos**: Probar el camino feliz (éxito) y al menos un camino de error (ej. formulario inválido, API externa caída).
- **Nuevos Campos**: Si se añade un campo a un modelo con `default`, asegurar que los tests de creación existentes no fallen (usar `required=False` en forms si aplica).

## Estructura de un Test
Patrón Arrange / Act / Assert. Estilo pytest (funciones con fixtures):

```python
from unittest.mock import patch
import pytest

@pytest.mark.django_db
def test_crear_investigacion_con_datos_validos_redirige_al_detalle(client, django_user_model):
    # Arrange: preparar datos y mocks
    usuario = django_user_model.objects.create_user("ana", password="x")
    client.force_login(usuario)

    # Act: ejecutar la acción
    with patch("apps.engine.services.buscar_contenido") as buscar:
        buscar.return_value = []
        respuesta = client.post("/investigacion/crear/", {"nombre": "Competencia SEO"})

    # Assert: verificar el estado final
    assert respuesta.status_code == 302
    assert Investigacion.objects.filter(nombre="Competencia SEO").exists()
```

Si la clase de test hereda de `TestCase`, usar `self.client` y `self.assert...` con la misma estructura. No mezclar `self` en funciones sueltas de pytest.

Nombres: `test_<qué_se_prueba>_<condición>_<resultado_esperado>`.
