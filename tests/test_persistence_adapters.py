"""Prueba de integración del adaptador de persistencia de Django.

Requiere django.setup() y la base de datos de prueba de pytest-django.
Verifica que el adaptador guarda en BD real, recupera y actualiza estado.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from apps.core.models import Agente, Habilidad, Tarea  # noqa: E402
from arm.adapters.persistence import TaskData  # noqa: E402
from arm_django.adapters import DjangoExecutionRepository, DjangoTaskRepository  # noqa: E402


def _crear_tarea_en_bd(estado: str = "cola") -> Tarea:
    agente, _ = Agente.objects.get_or_create(
        nombre="Agente de prueba",
        defaults={"rol": "probador", "temperatura": 0.0},
    )
    habilidad, _ = Habilidad.objects.get_or_create(
        slug="habilidad-prueba",
        defaults={"nombre": "Habilidad de prueba", "instrucciones": "hacer algo"},
    )
    return Tarea.objects.create(
        estado=estado,
        agente=agente,
        habilidad=habilidad,
        payload={"clave": "valor"},
    )


@pytest.mark.django_db
def test_django_adapter_guarda_tarea_en_bd_y_actualiza_estado():
    """Crear, recuperar y actualizar una tarea con el adaptador de Django persiste en BD."""
    repo: DjangoTaskRepository = DjangoTaskRepository()
    habilidad, _ = Habilidad.objects.get_or_create(
        slug="habilidad-prueba-tarea",
        defaults={"nombre": "Habilidad prueba tarea", "instrucciones": "hacer algo"},
    )
    task = TaskData(
        estado="cola",
        payload={"clave": "valor"},
        intentos=0,
        habilidad_id=habilidad.id,
    )

    created = repo.create_task(task)
    assert created.id is not None
    assert created.estado == "cola"
    assert created.payload == {"clave": "valor"}
    assert created.habilidad_id == habilidad.id

    fetched = repo.get_task(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.estado == "cola"

    updated = repo.update_task_status(created.id, "ok")
    assert updated is not None
    assert updated.estado == "ok"

    tarea_bd = Tarea.objects.get(pk=created.id)
    assert tarea_bd.estado == "ok"

    # Limpieza de datos de prueba.
    Tarea.objects.filter(pk=created.id).delete()


@pytest.mark.django_db
def test_django_adapter_get_task_inexistente_devuelve_none():
    """Obtener una tarea inexistente con el adaptador de Django devuelve None."""
    repo: DjangoTaskRepository = DjangoTaskRepository()
    assert repo.get_task(999999) is None


@pytest.mark.django_db
def test_django_adapter_update_task_status_inexistente_devuelve_none():
    """Actualizar una tarea inexistente con el adaptador de Django devuelve None."""
    repo: DjangoTaskRepository = DjangoTaskRepository()
    assert repo.update_task_status(999999, "ok") is None


@pytest.mark.django_db
def test_django_execution_adapter_crea_y_recupera_ejecuciones():
    """Crear ejecuciones y recuperarlas por tarea con el adaptador de Django."""
    tarea = _crear_tarea_en_bd()
    try:
        repo_exec: DjangoExecutionRepository = DjangoExecutionRepository()
        ejec = repo_exec.create_execution(
            task_id=tarea.id,
            modelo_usado="modelo-prueba",
            tokens_in=10,
            tokens_out=5,
            ms=120,
            salida={"resultado": "ok"},
            error=None,
        )
        assert ejec is not None
        assert ejec.tarea_id == tarea.id
        assert ejec.tokens_in == 10

        execs = repo_exec.get_executions_by_task(tarea.id)
        assert len(execs) == 1
        assert execs[0].id == ejec.id
    finally:
        Tarea.objects.filter(pk=tarea.id).delete()
