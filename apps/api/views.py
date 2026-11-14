"""Endpoints de la API REST para integraciones externas (webhooks).

La autenticación se realiza mediante el header X-ARM-API-KEY comparado con
settings.ARM_API_KEY. Las vistas están exentas de CSRF porque son consumidas
por sistemas externos sin sesión Django.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import Agente, Habilidad, Tarea, IntegracionConfig
from apps.core.schemas import TareaCreateSchema
from apps.engine.tasks import ejecutar_tarea

logger = logging.getLogger(__name__)


def _hash_sha256(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def _autenticado(request) -> bool:
    """Verifica el header X-ARM-API-KEY contra el hash SHA-256 en BD.

    Busca la IntegracionConfig activa de tipo arm_api y compara en tiempo
    constante con hmac.compare_digest. Mientras no exista registro migrado en
    BD, se mantiene el fallback a settings.ARM_API_KEY
    (TODO C.5b: retirar este fallback al completar la migración de credenciales).
    """
    clave = request.headers.get("X-ARM-API-KEY")
    if not clave:
        return False

    hash_proporcionado = _hash_sha256(clave)

    integracion = (
        IntegracionConfig.objects.filter(tipo="arm_api", activa=True).first()
    )
    if integracion is not None:
        return hmac.compare_digest(hash_proporcionado, integracion.credenciales)

    # TODO C.5b: retirar este fallback una vez migrada la clave a IntegracionConfig.
    return clave == settings.ARM_API_KEY


@csrf_exempt
@require_POST
def webhook_crear_tarea(request):
    """Crea una tarea y la encola en Huey. Autenticación por header."""
    if not _autenticado(request):
        return JsonResponse({"error": "Autenticación requerida"}, status=401)

    try:
        cuerpo = json.loads(request.body or b"{}")
    except json.JSONDecodeError as error:
        return JsonResponse({"error": f"JSON inválido: {error}"}, status=400)

    try:
        schema = TareaCreateSchema(**cuerpo)
    except Exception as error:  # ValidationError de Pydantic v2
        return JsonResponse({"error": str(error)}, status=400)

    habilidad = Habilidad.objects.filter(slug=schema.habilidad_slug).first()
    if habilidad is None:
        return JsonResponse(
            {"error": f"Habilidad no encontrada: {schema.habilidad_slug}"},
            status=404,
        )

    agente = (
        Agente.objects.filter(modelo__activo=True, habilidades=habilidad)
        .select_related("modelo")
        .order_by("pk")
        .first()
    )
    if agente is None:
        return JsonResponse(
            {"error": "No hay agentes activos con esa habilidad"}, status=404
        )

    payload = {"texto": schema.texto}
    if schema.keyword:
        payload["keyword"] = schema.keyword
    if schema.instrucciones:
        payload["instrucciones"] = schema.instrucciones

    tarea = Tarea.objects.create(
        agente=agente,
        habilidad=habilidad,
        estado=Tarea.Estado.COLA,
        payload=payload,
    )
    ejecutar_tarea(tarea.pk)

    return JsonResponse(
        {
            "tarea_id": tarea.pk,
            "estado": "cola",
            "mensaje": "Tarea encolada correctamente",
        },
        status=201,
    )


@csrf_exempt
@require_GET
def consultar_tarea(request, pk: int):
    """Consulta el estado y el último artefacto de una tarea."""
    if not _autenticado(request):
        return JsonResponse({"error": "Autenticación requerida"}, status=401)

    tarea = Tarea.objects.filter(pk=pk).first()
    if tarea is None:
        return JsonResponse({"error": "Tarea no encontrada"}, status=404)

    ultimo_artefacto = tarea.artefactos.order_by("-id").first()
    artefacto = ultimo_artefacto.contenido if ultimo_artefacto else None

    return JsonResponse(
        {
            "tarea_id": tarea.pk,
            "estado": tarea.estado,
            "artefacto": artefacto,
        },
        status=200,
    )
