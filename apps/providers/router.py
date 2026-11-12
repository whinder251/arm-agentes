"""Router de modelos: caché primero y después prioridad con fallback."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Sequence

from apps.providers.base import (
    BaseProveedor,
    CuotaAgotada,
    ErrorProveedor,
    LimiteVelocidad,
    Messages,
    RespuestaChat,
)
from apps.providers.cache import CacheRespuestas
from apps.providers.gemini import GeminiProvider
from apps.providers.openrouter import OpenRouterProvider
from apps.providers.quota import CuotaDiaria

COOLDOWN_SEGUNDOS = 60

# El nombre del proveedor en la base selecciona el adaptador. Es provisional:
# lo razonable es guardar el tipo de adaptador en Proveedor en un paso futuro.
ADAPTADORES = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


def fabricar_proveedor(proveedor) -> BaseProveedor:
    """Crea el adaptador que corresponde al nombre del proveedor."""
    clase = ADAPTADORES.get(proveedor.nombre.strip().lower())
    if clase is None:
        raise ErrorProveedor(
            f"sin adaptador para el proveedor '{proveedor.nombre}'"
        )
    return clase(api_key=proveedor.api_key, base_url=proveedor.base_url)


class Router:
    """Prueba los modelos por prioridad con caché delante y cuota reservada."""

    def __init__(
        self,
        modelos: Sequence[Any],
        cache: CacheRespuestas | None = None,
        fabrica: Callable[[Any], BaseProveedor] = fabricar_proveedor,
        reloj: Callable[[], float] = time.monotonic,
    ):
        self.modelos = list(modelos)
        self.cache = cache if cache is not None else CacheRespuestas()
        self.fabrica = fabrica
        self.reloj = reloj
        self._cooldown: dict[Any, float] = {}

    def _clave_modelo(self, modelo) -> Any:
        return modelo.pk if modelo.pk is not None else modelo.model_id

    def _en_cooldown(self, modelo) -> bool:
        hasta = self._cooldown.get(self._clave_modelo(modelo))
        return hasta is not None and hasta > self.reloj()

    def completar(
        self,
        messages: Messages,
        config: Mapping[str, Any] | None = None,
    ) -> RespuestaChat:
        """Devuelve la primera respuesta válida de la lista de modelos."""
        for modelo in self.modelos:
            guardada = self.cache.get(messages, modelo.model_id, config)
            if guardada is not None:
                return guardada

        fallos: list[str] = []
        for modelo in self.modelos:
            if self._en_cooldown(modelo):
                fallos.append(f"{modelo.model_id}: en espera por límite de ritmo")
                continue

            cuota = CuotaDiaria(modelo.proveedor)
            if not cuota.reservar():
                fallos.append(f"{modelo.model_id}: sin cuota diaria")
                continue

            proveedor = None
            try:
                proveedor = self.fabrica(modelo.proveedor)
                respuesta = proveedor.chat(messages, modelo.model_id, config)
            except LimiteVelocidad:
                # El proveedor rechazó la petición sin consumirla.
                cuota.liberar()
                self._cooldown[self._clave_modelo(modelo)] = (
                    self.reloj() + COOLDOWN_SEGUNDOS
                )
                fallos.append(f"{modelo.model_id}: límite de velocidad")
                continue
            except ValueError as error:
                # Configuración inválida: no llegó a salir ninguna petición.
                cuota.liberar()
                fallos.append(f"{modelo.model_id}: {error}")
                continue
            except ErrorProveedor as error:
                # 5xx o timeout: la llamada pudo consumirse, no se libera.
                fallos.append(f"{modelo.model_id}: {error}")
                continue
            finally:
                if proveedor is not None:
                    proveedor.close()

            self.cache.set(messages, modelo.model_id, config, respuesta)
            return respuesta

        raise CuotaAgotada("ningún modelo respondió: " + "; ".join(fallos))
