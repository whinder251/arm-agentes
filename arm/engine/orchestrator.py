"""Orquestador independiente del núcleo ARM.

Coordina la ejecución de un paso usando un ToolGateway y repositorios de
persistencia, sin depender de Django ni de ningún ORM.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from arm.adapters.persistence import (
    ExecutionRepository,
    TaskData,
    TaskRepository,
)
from arm.core.contracts import ToolExecutionResult
from arm.tools.gateway import ToolGateway


class Orchestrator:
    """Orquesta la ejecución de un paso de tarea."""

    def __init__(
        self,
        task_repository: TaskRepository,
        execution_repository: ExecutionRepository,
        tool_gateway: ToolGateway,
    ) -> None:
        self.task_repository = task_repository
        self.execution_repository = execution_repository
        self.tool_gateway = tool_gateway

    def execute_step(
        self, task_id: int, tool_slug: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ejecuta el ciclo básico de un paso.

        1. Obtiene la tarea del repositorio.
        2. Registra una ejecución.
        3. Llama al ToolGateway con la herramienta y los parámetros.
        4. Actualiza el estado de la tarea según el resultado.
        """
        task: Optional[TaskData] = self.task_repository.get_task(task_id)
        if task is None:
            return {
                "ok": False,
                "task_id": task_id,
                "estado": None,
                "error": f"Tarea {task_id} no encontrada",
            }

        # Registrar la ejecución (inicio)
        self.execution_repository.create_execution(
            task_id=task_id,
            modelo_usado="mock",
            tokens_in=0,
            tokens_out=0,
            ms=0,
            salida=None,
            error=None,
        )

        # Llamar al gateway
        resultado: ToolExecutionResult = self.tool_gateway.execute(
            tool_slug, params
        )

        nuevo_estado = "ok" if resultado.success else "error"
        updated_task = self.task_repository.update_task_status(
            task_id, nuevo_estado
        )
        if updated_task is None:
            return {
                "ok": False,
                "task_id": task_id,
                "estado": None,
                "error": f"Tarea {task_id} no se pudo actualizar",
            }

        return {
            "ok": resultado.success,
            "task_id": task_id,
            "estado": nuevo_estado,
            "resultado": resultado.data,
            "error": resultado.error,
        }
