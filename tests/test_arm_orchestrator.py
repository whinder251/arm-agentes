"""Pruebas aisladas del Orchestrator del núcleo ARM.

100% sin Django, sin django.setup(), sin base de datos.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from arm.adapters.persistence import (
    ExecutionRepository,
    TaskData,
    TaskRepository,
)
from arm.core.contracts import ToolExecutionResult, ToolSpec
from arm.engine.orchestrator import Orchestrator
from arm.tools.gateway import ToolGateway


class MockTaskRepository:
    def __init__(self) -> None:
        self._store: Dict[int, TaskData] = {}
        self._next_id = 1

    def create_task(self, task: TaskData) -> TaskData:
        task.id = self._next_id
        self._next_id += 1
        self._store[task.id] = task
        return task

    def get_task(self, task_id: int) -> Optional[TaskData]:
        return self._store.get(task_id)

    def update_task_status(self, task_id: int, estado: str) -> Optional[TaskData]:
        task = self._store.get(task_id)
        if task is None:
            return None
        task.estado = estado
        return task


class MockExecutionRepository:
    def __init__(self) -> None:
        self._store: List[Any] = []

    def create_execution(
        self,
        task_id: int,
        modelo_usado: str,
        tokens_in: int,
        tokens_out: int,
        ms: int,
        salida: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Any:
        exec_obj: Dict[str, Any] = {
            "task_id": task_id,
            "modelo_usado": modelo_usado,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "ms": ms,
            "salida": salida,
            "error": error,
        }
        self._store.append(exec_obj)
        return exec_obj

    def get_executions_by_task(self, task_id: int) -> List[Any]:
        return [e for e in self._store if e["task_id"] == task_id]


def _gateway_con_herramienta_exitosa() -> ToolGateway:
    gateway = ToolGateway()
    gateway.register(
        ToolSpec(
            slug="herramienta-ok",
            nombre="Herramienta OK",
            descripcion="Siempre tiene éxito",
            input_schema={},
            output_schema={},
            requiere_credencial=False,
            efecto_externo=False,
        )
    )
    return gateway


def _gateway_con_herramienta_fallida() -> ToolGateway:
    gateway = ToolGateway()
    gateway.register(
        ToolSpec(
            slug="herramienta-error",
            nombre="Herramienta Error",
            descripcion="Siempre falla validación",
            input_schema={"valor": "str"},
            output_schema={},
            requiere_credencial=False,
            efecto_externo=False,
        )
    )
    return gateway


def test_orchestrator_execute_step_exito():
    """execute_step con herramienta que tiene éxito actualiza estado a 'ok'."""
    task_repo = MockTaskRepository()
    exec_repo = MockExecutionRepository()
    gateway = _gateway_con_herramienta_exitosa()

    task = task_repo.create_task(TaskData(estado="cola", payload={}))
    orchestrator = Orchestrator(task_repo, exec_repo, gateway)

    resultado = orchestrator.execute_step(task.id, "herramienta-ok", {})

    assert resultado["ok"] is True
    assert resultado["estado"] == "ok"
    assert resultado["error"] is None

    tarea_actualizada = task_repo.get_task(task.id)
    assert tarea_actualizada is not None
    assert tarea_actualizada.estado == "ok"

    ejecuciones = exec_repo.get_executions_by_task(task.id)
    assert len(ejecuciones) == 1


def test_orchestrator_execute_step_fallo_validacion():
    """execute_step con herramienta que falla validación actualiza estado a 'error'."""
    task_repo = MockTaskRepository()
    exec_repo = MockExecutionRepository()
    gateway = _gateway_con_herramienta_fallida()

    task = task_repo.create_task(TaskData(estado="cola", payload={}))
    orchestrator = Orchestrator(task_repo, exec_repo, gateway)

    resultado = orchestrator.execute_step(
        task.id, "herramienta-error", {"valor": 123}
    )

    assert resultado["ok"] is False
    assert resultado["estado"] == "error"
    assert resultado["error"] is not None

    tarea_actualizada = task_repo.get_task(task.id)
    assert tarea_actualizada is not None
    assert tarea_actualizada.estado == "error"


def test_orchestrator_tarea_inexistente():
    """execute_step con tarea inexistente retorna error sin actualizar."""
    task_repo = MockTaskRepository()
    exec_repo = MockExecutionRepository()
    gateway = _gateway_con_herramienta_exitosa()

    orchestrator = Orchestrator(task_repo, exec_repo, gateway)

    resultado = orchestrator.execute_step(999, "herramienta-ok", {})

    assert resultado["ok"] is False
    assert resultado["estado"] is None
    assert "no encontrada" in resultado["error"]
