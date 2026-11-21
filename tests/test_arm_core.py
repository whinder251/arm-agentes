"""Pruebas unitarias puras de Python para el Tool Gateway de ARM.

Sin django.setup(), sin imports de apps/, sin Django, sin base de datos.
"""

import os
import sys

# Asegurar que el paquete arm sea importable sin instalarlo con pip
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError

from arm.core.contracts import ToolSpec, ToolExecutionResult
from arm.tools.gateway import ToolGateway


def test_registro_y_ejecucion_valida():
    """Registro de herramienta y ejecución con input correcto pasa validación."""
    gateway = ToolGateway()
    spec = ToolSpec(
        slug="consultar_clima",
        nombre="Consultar clima",
        descripcion="Obtiene el clima de una ciudad",
        input_schema={"ciudad": "str", "pais": "str"},
        output_schema={"temperatura": "float", "condicion": "str"},
        requiere_credencial=True,
        efecto_externo=False,
    )
    gateway.register(spec)

    resultado = gateway.execute("consultar_clima", {"ciudad": "Madrid", "pais": "ES"})

    assert isinstance(resultado, ToolExecutionResult)
    assert resultado.success is True
    assert resultado.data == {"mock": "ok"}
    assert resultado.error is None


def test_ejecucion_input_invalido_retorna_error_validacion():
    """Ejecución con input incorrecto retorna error de validación de Pydantic."""
    gateway = ToolGateway()
    spec = ToolSpec(
        slug="consultar_clima",
        nombre="Consultar clima",
        descripcion="Obtiene el clima de una ciudad",
        input_schema={"ciudad": "str", "pais": "str"},
        output_schema={},
        requiere_credencial=False,
        efecto_externo=False,
    )
    gateway.register(spec)

    resultado = gateway.execute("consultar_clima", {"ciudad": 123, "pais": "ES"})

    assert resultado.success is False
    assert resultado.error is not None
    assert "ciudad" in resultado.error


def test_herramienta_no_registrada_retorna_error():
    """Ejecutar una herramienta que no está registrada retorna error sin lanzar excepción."""
    gateway = ToolGateway()

    resultado = gateway.execute("inexistente", {})

    assert resultado.success is False
    assert resultado.error is not None
    assert "no registrada" in resultado.error
