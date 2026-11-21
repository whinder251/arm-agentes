"""Adaptadores de persistencia de Django para los puertos del núcleo ARM.

Implementa TaskRepository y ExecutionRepository sobre los modelos existentes
Tarea y Ejecucion de apps.core.models, mapeando hacia/desde TaskData del núcleo.
"""

from typing import Any, Dict, List, Optional

import django
from apps.core.models import Ejecucion, Tarea

from arm.adapters.persistence import ExecutionRepository, TaskData, TaskRepository


class DjangoTaskRepository:
    """Implementación de TaskRepository sobre el modelo Tarea de Django."""

    def create_task(self, task: TaskData) -> TaskData:
        tarea = Tarea.objects.create(
            estado=task.estado,
            agente=None,
            habilidad_id=task.habilidad_id,
            payload=task.payload,
            intentos=task.intentos,
        )
        return TaskData(
            id=tarea.id,
            estado=tarea.estado,
            payload=tarea.payload,
            intentos=tarea.intentos,
            habilidad_id=tarea.habilidad_id,
        )

    def get_task(self, task_id: int) -> Optional[TaskData]:
        try:
            tarea = Tarea.objects.get(pk=task_id)
        except Tarea.DoesNotExist:
            return None
        return TaskData(
            id=tarea.id,
            estado=tarea.estado,
            payload=tarea.payload,
            intentos=tarea.intentos,
            habilidad_id=tarea.habilidad_id,
        )

    def update_task_status(self, task_id: int, estado: str) -> Optional[TaskData]:
        try:
            tarea = Tarea.objects.get(pk=task_id)
        except Tarea.DoesNotExist:
            return None
        tarea.estado = estado
        tarea.save(update_fields=["estado", "actualizado_en"])
        return TaskData(
            id=tarea.id,
            estado=tarea.estado,
            payload=tarea.payload,
            intentos=tarea.intentos,
            habilidad_id=tarea.habilidad_id,
        )


class DjangoExecutionRepository:
    """Implementación de ExecutionRepository sobre el modelo Ejecucion de Django."""

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
        try:
            tarea = Tarea.objects.get(pk=task_id)
        except Tarea.DoesNotExist:
            return None
        ejecucion = Ejecucion.objects.create(
            tarea=tarea,
            modelo_usado=modelo_usado,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            ms=ms,
            salida=salida,
            error=error if error is not None else "",
        )
        return ejecucion

    def get_executions_by_task(self, task_id: int) -> List[Any]:
        return list(
            Ejecucion.objects.filter(tarea_id=task_id).order_by("id")
        )
