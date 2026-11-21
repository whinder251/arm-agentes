"""Pruebas unitarias aisladas del núcleo de persistencia de ARM.

Sin django.setup(), sin imports de apps/, sin Django, sin base de datos.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arm.adapters.persistence import TaskData, TaskRepository


class MockTaskRepository:
    """Repositorio en memoria que implementa TaskRepository para pruebas aisladas."""

    def __init__(self) -> None:
        self._store: dict[int, TaskData] = {}
        self._next_id = 1

    def create_task(self, task: TaskData) -> TaskData:
        task.id = self._next_id
        self._next_id += 1
        self._store[task.id] = task
        return task

    def get_task(self, task_id: int) -> OptionalTaskData:
        return self._store.get(task_id)

    def update_task_status(self, task_id: int, estado: str) -> OptionalTaskData:
        task = self._store.get(task_id)
        if task is None:
            return None
        task.estado = estado
        return task


# Alias legible para Optional[TaskData] en anotaciones del mock.
OptionalTaskData = Optional[TaskData]


def test_mock_create_task_asigna_id_y_devuelve_datos():
    """Crear una tarea con el mock la persiste en memoria y le asigna id."""
    repo: TaskRepository = MockTaskRepository()
    task = TaskData(estado="cola", payload={"clave": "valor"}, intentos=0)
    created = repo.create_task(task)

    assert created.id == 1
    assert created.estado == "cola"
    assert created.payload == {"clave": "valor"}
    assert created.intentos == 0


def test_mock_get_task_devuelve_tarea_creada():
    """Obtener una tarea existente devuelve sus datos."""
    repo: TaskRepository = MockTaskRepository()
    repo.create_task(TaskData(estado="cola", payload={"a": 1}))
    fetched = repo.get_task(1)

    assert fetched is not None
    assert fetched.id == 1
    assert fetched.estado == "cola"


def test_mock_get_task_inexistente_devuelve_none():
    """Obtener una tarea que no existe devuelve None sin lanzar excepción."""
    repo: TaskRepository = MockTaskRepository()
    assert repo.get_task(999) is None


def test_mock_update_task_status_cambia_estado():
    """Actualizar el estado de una tarea existente lo persiste en memoria."""
    repo: TaskRepository = MockTaskRepository()
    repo.create_task(TaskData(estado="cola"))
    updated = repo.update_task_status(1, "ok")

    assert updated is not None
    assert updated.estado == "ok"
    assert repo.get_task(1).estado == "ok"


def test_mock_update_task_status_inexistente_devuelve_none():
    """Actualizar una tarea inexistente devuelve None sin lanzar excepción."""
    repo: TaskRepository = MockTaskRepository()
    assert repo.update_task_status(999, "ok") is None
