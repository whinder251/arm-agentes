"""Pruebas de la tarea periódica de investigaciones programadas (Paso UX-3).

La lógica de fechas se prueba sobre el helper puro ``_debe_ejecutar``. Las
pruebas de la tarea usan ``call_local`` y mockean la ejecución real para no
tocar la red.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.models import InvestigacionProgramada
from apps.engine import tasks


def _crear_investigacion(**kwargs):
    datos = {
        "nombre": "Investigación de prueba",
        "urls_objetivo": "https://ejemplo.com/feed.rss",
        "frecuencia": "diaria",
        "activa": True,
    }
    datos.update(kwargs)
    return InvestigacionProgramada.objects.create(**datos)


class TestDebeEjecutar:
    def test_sin_ultima_ejecucion_ejecuta(self):
        ahora = timezone.now()
        investigacion = InvestigacionProgramada(
            frecuencia="diaria", ultima_ejecucion=None
        )

        assert tasks._debe_ejecutar(investigacion, ahora) is True

    @pytest.mark.parametrize(
        ("frecuencia", "delta", "esperado"),
        [
            ("diaria", timedelta(hours=25), True),
            ("diaria", timedelta(hours=23), False),
            ("semanal", timedelta(days=7), True),
            ("semanal", timedelta(days=6, hours=23), False),
            ("mensual", timedelta(days=30), True),
            ("mensual", timedelta(days=29), False),
        ],
    )
    def test_periodo_segun_frecuencia(self, frecuencia, delta, esperado):
        ahora = timezone.now()
        investigacion = InvestigacionProgramada(
            frecuencia=frecuencia,
            ultima_ejecucion=ahora - delta,
        )

        assert tasks._debe_ejecutar(investigacion, ahora) is esperado


@pytest.mark.django_db
class TestChequearYEjecutarInvestigaciones:
    def test_ejecuta_solo_activas_y_vencidas(self):
        ahora = timezone.now()
        vencida = _crear_investigacion(
            nombre="Vencida",
            ultima_ejecucion=ahora - timedelta(days=2),
        )
        _crear_investigacion(
            nombre="Reciente",
            ultima_ejecucion=ahora - timedelta(hours=1),
        )
        _crear_investigacion(
            nombre="Inactiva",
            activa=False,
            ultima_ejecucion=None,
        )

        with patch("apps.engine.tasks.ejecutar_investigacion") as mock_ejecutar:
            resultado = tasks.chequear_y_ejecutar_investigaciones.call_local()

        assert resultado == 1
        mock_ejecutar.assert_called_once_with(vencida)

    def test_error_en_una_investigacion_no_detiene_las_demas(self):
        ahora = timezone.now()
        primera = _crear_investigacion(
            nombre="Falla",
            ultima_ejecucion=ahora - timedelta(days=2),
        )
        segunda = _crear_investigacion(
            nombre="Continúa",
            ultima_ejecucion=ahora - timedelta(days=2),
        )

        def ejecutar(investigacion):
            if investigacion.pk == primera.pk:
                raise RuntimeError("fallo simulado")
            return {"ejecutadas": 1, "hallazgos_nuevos": 0, "fallos": []}

        with patch(
            "apps.engine.tasks.ejecutar_investigacion", side_effect=ejecutar
        ) as mock_ejecutar:
            resultado = tasks.chequear_y_ejecutar_investigaciones.call_local()

        assert resultado == 1
        assert mock_ejecutar.call_count == 2
        ejecutadas = [llamada.args[0] for llamada in mock_ejecutar.call_args_list]
        assert primera in ejecutadas
        assert segunda in ejecutadas


def test_tarea_registrada_en_huey():
    from huey.contrib.djhuey import HUEY

    assert (
        "apps.engine.tasks.chequear_y_ejecutar_investigaciones"
        in HUEY._registry._registry
    )
