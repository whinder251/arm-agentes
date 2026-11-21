"""Wrapper de Django para el Orchestrator del núcleo ARM."""

from __future__ import annotations

from arm.engine.orchestrator import Orchestrator
from arm.tools.gateway import ToolGateway
from arm_django.adapters import DjangoExecutionRepository, DjangoTaskRepository


def ejecutar_paso_orquestado(
    task_id: int,
    tool_slug: str,
    params: dict,
    gateway: ToolGateway | None = None,
) -> dict:
    """Ejecuta un paso orquestado usando adaptadores de Django.

    Instancia el Orchestrator con DjangoTaskRepository,
    DjangoExecutionRepository y el ToolGateway proporcionado (o uno vacío
    si no se pasa ninguno).
    """
    if gateway is None:
        gateway = ToolGateway()

    task_repository = DjangoTaskRepository()
    execution_repository = DjangoExecutionRepository()

    orchestrator = Orchestrator(
        task_repository=task_repository,
        execution_repository=execution_repository,
        tool_gateway=gateway,
    )
    return orchestrator.execute_step(task_id, tool_slug, params)
