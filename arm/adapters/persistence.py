"""Interfaces de repositorios de persistencia para el núcleo independiente de ARM.

Este archivo define los puertos (Protocol) que el Engine usará para persistir
tareas y ejecuciones, sin depender de Django ni de ningún ORM. Las implementaciones
concretas (por ejemplo, sobre modelos Django) viven en paquetes separados como
arm_django.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class TaskData:
    """Objeto de datos simple que representa una tarea en el núcleo.

    No está ligado a ningún modelo Django; sirve como contrato de transferencia
    entre el Engine y los adaptadores de persistencia.
    """

    def __init__(
        self,
        estado: str,
        payload: Optional[Dict[str, Any]] = None,
        intentos: int = 0,
        id: Optional[int] = None,
        habilidad_id: Optional[int] = None,
    ) -> None:
        self.id = id
        self.estado = estado
        self.payload = payload if payload is not None else {}
        self.intentos = intentos
        self.habilidad_id = habilidad_id


@runtime_checkable
class TaskRepository(Protocol):
    """Puerto de persistencia para tareas."""

    def create_task(self, task: TaskData) -> TaskData:
        """Crea una tarea y la devuelve con su identificador asignado."""
        ...

    def get_task(self, task_id: int) -> Optional[TaskData]:
        """Obtiene una tarea por su identificador, o None si no existe."""
        ...

    def update_task_status(self, task_id: int, estado: str) -> Optional[TaskData]:
        """Actualiza el estado de una tarea y la devuelve, o None si no existe."""
        ...


@runtime_checkable
class ExecutionRepository(Protocol):
    """Puerto de persistencia para ejecuciones de una tarea."""

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
        """Crea una ejecución asociada a una tarea."""
        ...

    def get_executions_by_task(self, task_id: int) -> List[Any]:
        """Devuelve todas las ejecuciones de una tarea, ordenadas por creación."""
        ...
