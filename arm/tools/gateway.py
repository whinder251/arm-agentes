"""Tool Gateway: registro en memoria y ejecución de herramientas con validación de esquema."""

from typing import Any
from pydantic import BaseModel, ValidationError, create_model

from arm.core.contracts import ToolSpec, ToolExecutionResult


class ToolGateway:
    """Gateway de herramientas con registro en memoria.

    Valida los parámetros de entrada contra el input_schema de cada ToolSpec
    antes de ejecutar (por ahora, mock de éxito).
    """

    def __init__(self) -> None:
        self._registry: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Registra una herramienta por su slug."""
        self._registry[spec.slug] = spec

    def execute(self, slug: str, params: dict) -> ToolExecutionResult:
        """Ejecuta una herramienta registrada.

        Valida params contra spec.input_schema con Pydantic v2.
        Si falla la validación, retorna ToolExecutionResult con success=False.
        Si pasa, retorna un mock de éxito.
        """
        spec = self._registry.get(slug)
        if spec is None:
            return ToolExecutionResult(
                success=False,
                data=None,
                error=f"Herramienta no registrada: {slug}",
            )

        try:
            self._validar_esquema(spec.input_schema, params)
        except ValidationError as exc:
            return ToolExecutionResult(
                success=False,
                data=None,
                error=str(exc),
            )

        return ToolExecutionResult(
            success=True,
            data={"mock": "ok"},
            error=None,
        )

    @staticmethod
    def _validar_esquema(esquema: dict, params: dict) -> Any:
        """Valida params contra un esquema de entrada usando Pydantic v2."""
        if not esquema:
            return params

        _TIPOS_PYTHON = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
        }

        campos = {}
        for nombre, tipo in esquema.items():
            if isinstance(tipo, str):
                tipo_python = _TIPOS_PYTHON.get(tipo, Any)
            else:
                tipo_python = Any
            campos[nombre] = (tipo_python, ...)

        modelo_validacion = create_model("InputSchema", **campos)
        return modelo_validacion.model_validate(params, strict=True)
