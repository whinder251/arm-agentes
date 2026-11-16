"""Motor de ejecución: tareas Huey con latido, reintentos y recuperación."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import timedelta
from typing import Any, Literal

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from apps.core.models import (
    Agente,
    Artefacto,
    Ejecucion,
    FormatoSalida,
    Habilidad,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Tarea,
    Workflow,
)
from apps.core.schemas import ErrorEstructurado, ResultadoAgente
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
            "content": _renderizar(tarea.habilidad.instrucciones, tarea.payload),
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


def _extraer_json_bloque(texto: str) -> str | None:
    """Extrae el primer bloque de JSON entre ````json y ```` si existe."""
    patron = r"```json\s*\n(.*?)\n\s*```"
    match = re.search(patron, texto, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _normalizar_respuesta(
    texto: str, formato_salida: FormatoSalida | None
) -> tuple[ResultadoAgente, dict[str, Any] | None, str]:
    """Normaliza la respuesta del proveedor usando el contrato Pydantic.

    Devuelve (resultado, datos_extraidos, crudo_guardar).
    """
    datos: dict[str, Any] | None = None
    error: ErrorEstructurado | None = None
    status: Literal["completed", "partial", "failed"] = "completed"
    success = True

    # a) Intento directo de parseo JSON.
    candidato: Any = None
    try:
        candidato = json.loads(texto)
    except (json.JSONDecodeError, TypeError, ValueError):
        # b) Extraer bloque entre ```json y ```.
        bloque = _extraer_json_bloque(texto)
        if bloque is not None:
            try:
                candidato = json.loads(bloque)
            except (json.JSONDecodeError, TypeError, ValueError):
                candidato = None

    if candidato is None or not isinstance(candidato, dict):
        # No hay JSON válido: marcar como failed sin romper el flujo.
        success = False
        status = "failed"
        error = ErrorEstructurado(
            code="respuesta_no_json",
            message="El modelo no devolvió un objeto JSON válido.",
            details=None,
        )
        resultado = ResultadoAgente(
            success=success,
            status=status,
            data=None,
            error=error,
            metadata={"contenido": texto},
        )
        return resultado, None, texto

    datos = candidato

    # Validación ligera contra el esquema de formato de salida si existe.
    esquema = formato_salida.esquema if formato_salida else {}
    if esquema:
        try:
            required = (
                esquema.get("required", []) if isinstance(esquema, dict) else []
            )
            faltantes = [k for k in required if k not in datos]
            if faltantes:
                if formato_salida and formato_salida.permite_parcial:
                    status = "partial"
                    success = True
                    error = ErrorEstructurado(
                        code="campos_faltantes",
                        message="Faltan campos requeridos del esquema.",
                        details={"faltantes": faltantes},
                    )
                else:
                    status = "failed"
                    success = False
                    error = ErrorEstructurado(
                        code="campos_faltantes",
                        message="Faltan campos requeridos del esquema.",
                        details={"faltantes": faltantes},
                    )
        except Exception:
            # Si el esquema no es válido, no se rompe el flujo.
            pass

    resultado = ResultadoAgente(
        success=success,
        status=status,
        data=datos,
        error=error,
        metadata={},
    )
    return resultado, datos, texto


def _obtener_formato_salida(tarea: Tarea) -> FormatoSalida | None:
    """Resuelve el FormatoSalida: override de la tarea, luego del agente, luego None."""
    if tarea.formato_salida_id:
        return tarea.formato_salida
    if tarea.agente_id and tarea.agente.formato_salida_id:
        return tarea.agente.formato_salida
    return None


def _guardar_artefacto(
    tarea: Tarea, respuesta, ejecucion: Ejecucion
) -> Artefacto:
    version = (
        tarea.artefactos.order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    metadata = {
        "modelo": respuesta.modelo,
        "tokens_in": respuesta.tokens_in,
        "tokens_out": respuesta.tokens_out,
        "ejecucion": ejecucion.pk,
    }
    formato_salida = _obtener_formato_salida(tarea)
    resultado, datos, crudo = _normalizar_respuesta(respuesta.texto, formato_salida)
    metadata["resultado"] = resultado.model_dump()
    if datos:
        # Extraer texto plano con prioridad cuando el JSON no cumple el esquema:
        # contenido > cuerpo > texto > texto_reescrito > fallback crudo.
        contenido_texto = respuesta.texto
        if isinstance(datos, dict):
            for clave in ['contenido', 'cuerpo', 'texto', 'texto_reescrito']:
                if clave in datos and isinstance(datos[clave], str):
                    contenido_texto = datos[clave]
                    break
        metadata.update({
            "titulo": str(datos.get("titulo", "") or ""),
            "slug": str(datos.get("slug", "") or ""),
            "contenido": contenido_texto,
            "meta_description": str(datos.get("meta_description", "") or ""),
            "focus_keyword": str(datos.get("focus_keyword", "") or ""),
        })
    else:
        contenido_texto = respuesta.texto
        metadata["contenido"] = respuesta.texto
    raw_response_val: str | None = crudo if getattr(settings, "ARM_GUARDAR_RAW", False) else None
    return Artefacto.objects.create(
        tarea=tarea,
        version=version,
        contenido=contenido_texto,
        metadata=metadata,
        raw_response=raw_response_val,
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
        Tarea.objects.select_related(
            "agente__modelo",
            "agente__formato_salida",
            "habilidad",
            "formato_salida",
            "paso_workflow__habilidad",
        )
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
        _marcar_latido(tarea_id)

        paso = tarea.paso_workflow
        modo_manual = tarea.habilidad.modo_ejecucion == "manual"

        # Leer el ResultadoAgente del artefacto recién creado para decidir el estado.
        ultimo_artefacto = (
            Artefacto.objects.filter(tarea=tarea)
            .order_by("-version")
            .first()
        )
        resultado = {}
        if ultimo_artefacto and ultimo_artefacto.metadata:
            resultado = ultimo_artefacto.metadata.get("resultado", {})
        status = resultado.get("status", "completed")

        # Modo manual siempre va a REVISION, independientemente del status (RB-010).
        if modo_manual:
            tarea.transicionar(Tarea.Estado.REVISION)
            return "revision"

        # Tareas automáticas: respetar el status del normalizador.
        if status == "failed":
            tarea.transicionar(Tarea.Estado.ERROR)
            # Propagar fallo al workflow padre si corresponde.
            if paso is not None:
                paso.workflow.estado = "fallido"
                paso.workflow.save(update_fields=["estado"])
            return "error"
        elif status == "partial":
            tarea.transicionar(Tarea.Estado.REVISION)
            return "revision"
        else:
            tarea.transicionar(Tarea.Estado.OK)
            # Orquestación: al terminar un paso en 'ok', encolar el siguiente
            # paso del workflow automáticamente (solo modo auto).
            if paso is not None:
                continuar_workflow(paso.workflow.pk, paso.orden + 1)
            return "ok"
    except Exception as error:  # El worker no debe morir por una tarea.
        logger.exception("Tarea %s falló durante la ejecución", tarea_id)
        ejecucion.error = str(error)
        ejecucion.ms = int((time.monotonic() - inicio) * 1000)
        ejecucion.save(update_fields=["error", "ms"])
        tarea.refresh_from_db(fields=["estado", "intentos"])
        _registrar_fallo(tarea)
        # Propagación de fallo: si la tarea pertenece a un paso de workflow,
        # marcar el workflow padre como 'fallido'.
        if tarea.paso_workflow_id is not None:
            paso = tarea.paso_workflow
            paso.workflow.estado = "fallido"
            paso.workflow.save(update_fields=["estado"])
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

    # Extraer datos del paso anterior para pasarlos al siguiente
    paso_anterior = (
        PasoWorkflow.objects.filter(workflow=workflow, orden=siguiente_orden - 1)
        .first()
    )
    datos_anteriores = {}
    if paso_anterior is not None:
        tarea_anterior = (
            Tarea.objects.filter(paso_workflow=paso_anterior)
            .order_by("-id")
            .first()
        )
        if tarea_anterior is not None:
            if tarea_anterior.estado in (
                Tarea.Estado.REVISION,
                Tarea.Estado.ERROR,
            ):
                logger.info(
                    "Workflow %s no continua: paso %s en estado %s",
                    workflow.pk,
                    paso_anterior.orden,
                    tarea_anterior.estado,
                )
                return "bloqueado"
            ultimo_artefacto = (
                Artefacto.objects.filter(tarea=tarea_anterior)
                .order_by("-version")
                .first()
            )
            if ultimo_artefacto and ultimo_artefacto.metadata:
                resultado = ultimo_artefacto.metadata.get("resultado", {})
                datos_anteriores = resultado.get("data", {}) or {}
                if not datos_anteriores:
                    datos_anteriores = {
                        k: v
                        for k, v in ultimo_artefacto.metadata.items()
                        if k
                        not in ("modelo", "tokens_in", "tokens_out", "ejecucion", "resultado")
                    }

    nueva_tarea = Tarea.objects.create(
        agente=agente,
        habilidad=paso.habilidad,
        estado=Tarea.Estado.COLA,
        payload={**datos_anteriores},
        paso_workflow=paso,
    )
    ejecutar_tarea(nueva_tarea.pk)
    return "encolado"
