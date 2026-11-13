"""Motor de ejecución: tareas Huey con latido, reintentos y recuperación."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from apps.core.models import (
    Agente,
    Artefacto,
    Ejecucion,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Tarea,
    Workflow,
)
from apps.providers.router import Router

logger = logging.getLogger(__name__)

LATIDO_SEGUNDOS = 30
UMBRAL_HUERFANA = timedelta(minutes=5)
MAX_REINTENTOS = 3
REINTENTO_SEGUNDOS = 60


def _marcar_latido(tarea_id: int) -> None:
    """Escribe el instante del último latido sin tocar el resto de la fila."""
    Tarea.objects.filter(pk=tarea_id).update(actualizado_en=timezone.now())


class Latido:
    """Actualiza actualizado_en cada 30 segundos mientras dura la ejecución."""

    def __init__(self, tarea_id: int, intervalo: float = LATIDO_SEGUNDOS):
        self.tarea_id = tarea_id
        self.intervalo = intervalo
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._latir, daemon=True)

    def _latir(self) -> None:
        close_old_connections()
        try:
            while not self._parar.wait(self.intervalo):
                _marcar_latido(self.tarea_id)
        finally:
            close_old_connections()

    def __enter__(self) -> "Latido":
        _marcar_latido(self.tarea_id)
        self._hilo.start()
        return self

    def __exit__(self, *exc_info) -> bool:
        self._parar.set()
        self._hilo.join(timeout=self.intervalo + 1)
        return False


def _renderizar(plantilla: str, payload: dict) -> str:
    """Sustituye las variables {{ nombre }} del prompt con el payload."""
    texto = plantilla
    for clave, valor in payload.items():
        if isinstance(valor, (dict, list)):
            valor = json.dumps(valor, ensure_ascii=False)
        texto = texto.replace("{{ " + clave + " }}", str(valor))
        texto = texto.replace("{{" + clave + "}}", str(valor))
    return texto


def _construir_mensajes(tarea: Tarea) -> list[dict[str, str]]:
    mensajes: list[dict[str, str]] = []
    if tarea.agente_id:
        mensajes.append({"role": "system", "content": tarea.agente.rol})
    mensajes.append(
        {
            "role": "user",
            "content": _renderizar(tarea.habilidad.plantilla_prompt, tarea.payload),
        }
    )
    return mensajes


def _config_agente(tarea: Tarea) -> dict[str, float] | None:
    if not tarea.agente_id:
        return None
    return {"temperature": tarea.agente.temperatura}


def _modelos_para(tarea: Tarea) -> list[ModeloLLM]:
    """Modelos activos por prioridad, con el modelo del agente delante."""
    modelos = list(
        ModeloLLM.objects.filter(activo=True)
        .select_related("proveedor")
        .order_by("prioridad", "model_id")
    )
    if tarea.agente_id and tarea.agente.modelo is not None:
        preferido = tarea.agente.modelo
        if preferido.activo:
            modelos = [preferido] + [
                modelo for modelo in modelos if modelo.pk != preferido.pk
            ]
    return modelos


def _guardar_artefacto(
    tarea: Tarea, respuesta, ejecucion: Ejecucion
) -> Artefacto:
    version = (
        tarea.artefactos.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    return Artefacto.objects.create(
        tarea=tarea,
        version=version,
        contenido=respuesta.texto,
        metadata={
            "modelo": respuesta.modelo,
            "tokens_in": respuesta.tokens_in,
            "tokens_out": respuesta.tokens_out,
            "ejecucion": ejecucion.pk,
        },
    )


def programar_reintento(tarea_id: int, intento: int) -> None:
    """Reencola una tarea con una clave de idempotencia por intento."""
    clave = f"tarea:{tarea_id}:intento:{intento}"
    ejecutar_tarea.schedule(
        args=(tarea_id,), delay=REINTENTO_SEGUNDOS, id=clave
    )


def _registrar_fallo(tarea: Tarea) -> None:
    """Devuelve la tarea a la cola o la cierra tras agotar los reintentos."""
    if tarea.intentos < MAX_REINTENTOS:
        tarea.intentos += 1
        tarea.estado = Tarea.Estado.COLA
        tarea.save(update_fields=["estado", "intentos", "actualizado_en"])
        programar_reintento(tarea.pk, tarea.intentos)
        return

    tarea.estado = Tarea.Estado.FALLO
    tarea.save(update_fields=["estado", "actualizado_en"])
    logger.error(
        "Tarea %s falló de forma definitiva tras %s reintentos",
        tarea.pk,
        tarea.intentos,
    )


@db_task()
def ejecutar_tarea(tarea_id: int) -> str:
    """Ejecuta una tarea de la cola y registra su resultado."""
    # Reclamo atómico: una entrega duplicada en estado distinto a "cola" se ignora.
    reclamada = Tarea.objects.filter(
        pk=tarea_id, estado=Tarea.Estado.COLA
    ).update(estado=Tarea.Estado.CURSO, actualizado_en=timezone.now())
    if not reclamada:
        logger.info("Tarea %s ignorada: no está en cola", tarea_id)
        return "ignorada"

    tarea = (
        Tarea.objects.select_related("agente__modelo", "habilidad")
        .filter(pk=tarea_id)
        .first()
    )
    if tarea is None:
        return "inexistente"

    ejecucion = Ejecucion.objects.create(tarea=tarea)
    inicio = time.monotonic()

    try:
        with Latido(tarea_id):
            router = Router(_modelos_para(tarea))
            respuesta = router.completar(
                _construir_mensajes(tarea), _config_agente(tarea)
            )

        ejecucion.modelo_usado = respuesta.modelo
        ejecucion.tokens_in = respuesta.tokens_in
        ejecucion.tokens_out = respuesta.tokens_out
        ejecucion.ms = int((time.monotonic() - inicio) * 1000)
        ejecucion.salida = {"texto": respuesta.texto}
        ejecucion.save()

        # Conteo de tokens reales al proveedor (RB-014). None se trata como 0.
        try:
            proveedor = tarea.agente.modelo.proveedor
            if proveedor is not None:
                tokens_in = ejecucion.tokens_in or 0
                tokens_out = ejecucion.tokens_out or 0
                proveedor.tokens_consumidos_hoy += tokens_in + tokens_out
                proveedor.save(update_fields=["tokens_consumidos_hoy"])
        except AttributeError:
            logger.warning(
                "Tarea %s no tiene proveedor asociado; no se contabilizan tokens",
                tarea.pk,
            )

        _guardar_artefacto(tarea, respuesta, ejecucion)
        tarea.transicionar(Tarea.Estado.REVISION)
        tarea.transicionar(Tarea.Estado.OK)
        _marcar_latido(tarea_id)
        # Orquestación: al terminar un paso en 'ok', encolar el siguiente
        # paso del workflow automáticamente (RB-011).
        if (
            tarea.estado == Tarea.Estado.OK
            and tarea.paso_workflow_id is not None
        ):
            continuar_workflow.delay(
                tarea.paso_workflow.workflow.pk, tarea.paso_workflow.orden + 1
            )
        return "ok"
    except Exception as error:  # El worker no debe morir por una tarea.
        logger.exception("Tarea %s falló durante la ejecución", tarea_id)
        ejecucion.error = str(error)
        ejecucion.ms = int((time.monotonic() - inicio) * 1000)
        ejecucion.save(update_fields=["error", "ms"])
        tarea.refresh_from_db(fields=["estado", "intentos"])
        _registrar_fallo(tarea)
        return "fallo"


def recuperar_huerfanas(ahora=None) -> int:
    """Reencola las tareas en curso cuyo último latido superó 5 minutos."""
    corte = (ahora or timezone.now()) - UMBRAL_HUERFANA
    huerfanas = Tarea.objects.filter(
        estado=Tarea.Estado.CURSO, actualizado_en__lt=corte
    )
    recuperadas = 0
    for tarea in huerfanas:
        tarea.refresh_from_db(fields=["estado", "intentos", "actualizado_en"])
        if tarea.estado != Tarea.Estado.CURSO or tarea.actualizado_en >= corte:
            continue
        _registrar_fallo(tarea)
        recuperadas += 1
    return recuperadas


@db_periodic_task(crontab(minute="*"))
def revisar_huerfanas() -> int:
    """Barrido periódico de tareas cuyo worker desapareció."""
    return recuperar_huerfanas()


@db_task()
def continuar_workflow(workflow_id: int, siguiente_orden: int) -> str:
    """Encola el siguiente paso de un workflow, o lo cierra si ya no hay pasos."""
    try:
        workflow = Workflow.objects.get(pk=workflow_id)
    except Workflow.DoesNotExist:
        logger.warning(
            "Workflow %s no existe, se ignora continuación", workflow_id
        )
        return "inexistente"
    if workflow.estado != "en_ejecucion":
        logger.info(
            "Workflow %s no está en ejecución (estado=%s)",
            workflow.pk,
            workflow.estado,
        )
        return "no_en_ejecucion"

    paso = (
        PasoWorkflow.objects.select_related("habilidad", "agente")
        .filter(workflow=workflow, orden=siguiente_orden)
        .first()
    )
    if paso is None:
        workflow.estado = "completado"
        workflow.save(update_fields=["estado"])
        return "completado"

    agente = paso.agente
    if agente is None:
        agente = (
            Agente.objects.filter(
                habilidades=paso.habilidad, modelo__activo=True
            )
            .select_related("modelo")
            .order_by("pk")
            .first()
        )
    if agente is None:
        logger.warning(
            "No hay agente disponible para el paso %s del workflow %s",
            paso.orden,
            workflow.pk,
        )
        return "sin_agente"
    if agente.modelo is None or not agente.modelo.activo:
        logger.warning(
            "El agente %s no tiene modelo activo para el paso %s del workflow %s",
            agente.nombre,
            paso.orden,
            workflow.pk,
        )
        return "sin_modelo_activo"

    nueva_tarea = Tarea.objects.create(
        agente=agente,
        habilidad=paso.habilidad,
        estado=Tarea.Estado.COLA,
        payload={},
        paso_workflow=paso,
    )
    ejecutar_tarea.delay(nueva_tarea.pk)
    return "encolado"
