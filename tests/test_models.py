import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction

from apps.core.models import Agente, Habilidad, ModeloLLM, Proveedor


def crear_proveedor(**extra):
    datos = {
        "nombre": "Gemini",
        "base_url": "https://example.invalid/v1",
        "api_key": "clave-de-prueba",
        "rpm": 15,
        "limite_diario": 1000,
    }
    datos.update(extra)
    return Proveedor.objects.create(**datos)


def crear_habilidad(**extra):
    datos = {
        "nombre": "SEO",
        "slug": "seo",
        "plantilla_prompt": "Reescribe el texto: {{ texto }}",
        "esquema_salida": {"type": "object", "properties": {"titulo": {"type": "string"}}},
    }
    datos.update(extra)
    return Habilidad.objects.create(**datos)


@pytest.mark.django_db
def test_crear_proveedor():
    proveedor = crear_proveedor()
    assert proveedor.pk is not None
    assert proveedor.api_key == "clave-de-prueba"
    assert proveedor.rpm == 15
    assert proveedor.limite_diario == 1000


@pytest.mark.django_db
def test_crear_modelo_llm():
    proveedor = crear_proveedor()
    modelo = ModeloLLM.objects.create(
        proveedor=proveedor,
        model_id="gemini-2.5-flash",
        prioridad=10,
        json_nativo=True,
    )
    assert modelo.pk is not None
    assert modelo.activo is True
    assert modelo.proveedor == proveedor
    assert proveedor.modelos.count() == 1


@pytest.mark.django_db
def test_crear_habilidad():
    habilidad = crear_habilidad()
    assert habilidad.pk is not None
    assert habilidad.slug == "seo"
    assert habilidad.esquema_salida["type"] == "object"


@pytest.mark.django_db
def test_slug_de_habilidad_es_unico():
    crear_habilidad()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            crear_habilidad(nombre="Otra SEO")


@pytest.mark.django_db
def test_crear_agente_sin_modelo():
    agente = Agente.objects.create(nombre="Redactor", rol="Eres redactor.")
    assert agente.pk is not None
    assert agente.modelo is None
    assert agente.temperatura == 0.7


@pytest.mark.django_db
def test_agente_y_habilidades_se_relacionan():
    proveedor = crear_proveedor()
    modelo = ModeloLLM.objects.create(proveedor=proveedor, model_id="gemini-2.5-flash")
    seo = crear_habilidad()
    estilo = crear_habilidad(nombre="Estilo", slug="estilo")
    agente = Agente.objects.create(
        nombre="Editor", rol="Eres editor.", modelo=modelo, temperatura=0.2
    )

    agente.habilidades.set([seo, estilo])

    assert agente.habilidades.count() == 2
    assert set(agente.habilidades.values_list("slug", flat=True)) == {"seo", "estilo"}
    assert seo.agentes.get() == agente


@pytest.mark.django_db
def test_admin_registra_los_cuatro_modelos():
    for modelo in (Proveedor, ModeloLLM, Habilidad, Agente):
        assert admin.site.is_registered(modelo)
