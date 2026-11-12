import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction

from apps.core.models import (
    Agente,
    Artefacto,
    Ejecucion,
    Habilidad,
    ModeloLLM,
    Proveedor,
    Tarea,
)


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


def crear_tarea(**extra):
    datos = {"payload": {"texto": "Artículo original"}}
    if "habilidad" not in extra:
        datos["habilidad"] = crear_habilidad()
    datos.update(extra)
    return Tarea.objects.create(**datos)


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


@pytest.mark.django_db
def test_crear_tarea_con_estado_por_defecto():
    tarea = crear_tarea()
    assert tarea.pk is not None
    assert tarea.estado == "cola"
    assert tarea.agente is None
    assert tarea.intentos == 0
    assert tarea.payload["texto"] == "Artículo original"


@pytest.mark.django_db
def test_transiciones_de_estado_validas():
    tarea = crear_tarea()

    tarea.transicionar("curso")
    tarea.refresh_from_db()
    assert tarea.estado == "curso"

    tarea.transicionar("revision")
    tarea.refresh_from_db()
    assert tarea.estado == "revision"

    tarea.transicionar("ok")
    tarea.refresh_from_db()
    assert tarea.estado == "ok"


@pytest.mark.django_db
def test_transicion_de_estado_invalida():
    tarea = crear_tarea()
    with pytest.raises(ValueError):
        tarea.transicionar("ok")
    tarea.refresh_from_db()
    assert tarea.estado == "cola"


@pytest.mark.django_db
def test_dependencias_entre_tareas():
    primera = crear_tarea()
    segunda = crear_tarea(habilidad=crear_habilidad(nombre="Estilo", slug="estilo"))

    segunda.depende_de.add(primera)

    assert segunda.depende_de.count() == 1
    assert primera.dependientes.get() == segunda
    # La relación es asimétrica: la primera no depende de la segunda.
    assert primera.depende_de.count() == 0


@pytest.mark.django_db
def test_crear_ejecucion_vinculada_a_tarea():
    tarea = crear_tarea()
    ejecucion = Ejecucion.objects.create(
        tarea=tarea,
        modelo_usado="gemini-2.5-flash",
        tokens_in=120,
        tokens_out=340,
        ms=950,
        salida={"titulo": "Reescritura"},
    )

    assert ejecucion.pk is not None
    assert ejecucion.tarea == tarea
    assert tarea.ejecuciones.count() == 1
    assert ejecucion.salida["titulo"] == "Reescritura"
    assert ejecucion.error == ""


@pytest.mark.django_db
def test_crear_artefacto_vinculado_a_tarea():
    tarea = crear_tarea()
    artefacto = Artefacto.objects.create(
        tarea=tarea,
        contenido="Texto reescrito",
        metadata={"seo": "ok"},
    )

    assert artefacto.pk is not None
    assert artefacto.tarea == tarea
    assert artefacto.version == 1
    assert tarea.artefactos.count() == 1
    assert artefacto.metadata["seo"] == "ok"


@pytest.mark.django_db
def test_admin_registra_modelos_de_trabajo():
    for modelo in (Tarea, Ejecucion, Artefacto):
        assert admin.site.is_registered(modelo)
