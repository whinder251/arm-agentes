"""Reserva atómica del cupo diario de un proveedor."""

import time

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import ContadorCuota

# SQLite no aplica SELECT ... FOR UPDATE y puede devolver "database is locked"
# cuando dos hilos escriben a la vez. Estos reintentos son solo para ese caso.
MAX_REINTENTOS = 5


class CuotaDiaria:
    """Contador diario de llamadas de un proveedor, guardado en la base."""

    def __init__(self, proveedor):
        self.proveedor = proveedor

    def _fecha(self):
        """Fecha local del día en curso, según TIME_ZONE."""
        return timezone.localdate()

    def _contador_id(self):
        """Devuelve el contador de hoy, creándolo si es el primer uso."""
        contador, _ = ContadorCuota.objects.get_or_create(
            proveedor=self.proveedor, fecha=self._fecha()
        )
        return contador.pk

    def reservar(self):
        """Reserva una llamada. Devuelve False si se agotó el cupo."""
        limite = self.proveedor.limite_diario
        if limite == 0:
            # En Proveedor, 0 significa sin límite diario.
            return True

        for intento in range(MAX_REINTENTOS):
            try:
                contador_id = self._contador_id()
                with transaction.atomic():
                    # En Postgres la fila queda bloqueada hasta el commit.
                    # En SQLite es un no-op; allí protege el UPDATE condicional.
                    ContadorCuota.objects.select_for_update().get(pk=contador_id)
                    actualizadas = ContadorCuota.objects.filter(
                        pk=contador_id, usadas__lt=limite
                    ).update(usadas=F("usadas") + 1)
                return actualizadas == 1
            except (IntegrityError, OperationalError) as error:
                if intento == MAX_REINTENTOS - 1:
                    raise
                if isinstance(error, OperationalError) and (
                    "locked" not in str(error).lower()
                ):
                    raise
                time.sleep(0.05)
        return False

    def liberar(self):
        """Devuelve una reserva que falló antes de consumir la llamada."""
        actualizadas = ContadorCuota.objects.filter(
            proveedor=self.proveedor, fecha=self._fecha(), usadas__gt=0
        ).update(usadas=F("usadas") - 1)
        return actualizadas == 1
