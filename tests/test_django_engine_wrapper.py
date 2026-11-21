"""Prueba de integración del wrapper de Django para el Orchestrator.

Requiere django.setup() y la base de datos de prueba de pytest-django.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from apps.core.models import Agente, Habilidad, Tarea
from arm.core.contracts import ToolSpec
from arm.tools.gateway import ToolGateway
from arm_django.engine_wrapper import ejecutar_paso_orquestado


@pytest.mark.django_db
def test_ejecutar_paso_orquestado_cambia_estado_y_registra_ejecucion():
    """Llamar al wrapper con una tarea real cambia su estado y registra ejecución."""
    agente, _ = Agente.objects.get_or_create(
        nombre="Agente wrapper",
        defaults={"rol": "probador", "temperatura": 0.0},
    )
    habilidad, _ = Habilidad.objects.get_or_create(
        slug="habilidad-wrapper",
        defaults={"nombre": "Habilidad wrapper", "instrucciones": "hacer algo"},
    )
    tarea = Tarea.objects.create(
        estado="cola",
        agente=agente,
        habilidad=habilidad,
        payload={},
    )

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

    resultado = ejecutar_paso_orquestado(
        task_id=tarea.id,
        tool_slug="herramienta-ok",
        params={},
        gateway=gateway,
    )

    assert resultado["ok"] is True
    assert resultado["estado"] == "ok"
    assert resultado["error"] is None

    tarea.refresh_from_db()
    assert tarea.estado == "ok"

    # Limpieza de datos de prueba.
    Tarea.objects.filter(pk=tarea.id).delete()


@pytest.mark.django_db
def test_ejecutar_paso_orquestado_tarea_inexistente():
    """Llamar con tarea inexistente retorna error sin fallar."""
    gateway = ToolGateway()
    resultado = ejecutar_paso_orquestado(
        task_id=999999,
        tool_slug="herramienta-ok",
        params={},
        gateway=gateway,
    )
    assert resultado["ok"] is False
    assert resultado["estado"] is None
