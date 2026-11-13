"""Pipeline editorial: reescritura, SEO y verificación determinista final."""

from __future__ import annotations

import re

from django.utils.text import slugify

from apps.checks.estilo import verificar_estilo
from apps.checks.hechos import anclar_hechos
from apps.checks.seo import verificar_seo
from apps.core.models import Artefacto, Habilidad, Tarea
from apps.engine.tasks import ejecutar_tarea

HIGH_SEVERITY = "alta"


def _latest_artifact(tarea: Tarea) -> Artefacto | None:
    return tarea.artefactos.order_by("-version").first()


def _plain_text(texto: str) -> str:
    """Quita marcas markdown y normaliza espacios para derivar campos SEO."""
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", texto, flags=re.MULTILINE)
    text = re.sub(r"[*_`>\[\]()]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_from_text(texto: str, limit: int = 60) -> str:
    """Toma la primera línea útil como título, sin superar el máximo SEO."""
    for line in texto.splitlines():
        clean = re.sub(r"^#{1,6}\s*", "", line.strip())
        if not clean:
            continue
        if len(clean) <= limit:
            return clean
        cut = clean[:limit].rsplit(" ", 1)[0].strip()
        return cut or clean[:limit]
    return ""


def _meta_from_text(texto: str, limit: int = 155) -> str:
    """Recorta el texto plano al máximo de la meta descripción."""
    clean = _plain_text(texto)
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip()


def _seo_payload(tarea: Tarea, artefacto: Artefacto) -> dict:
    """Deriva el payload SEO del texto reescrito, conservando metadatos."""
    payload = dict(tarea.payload)
    texto = artefacto.contenido
    keyword = str(payload.get("keyword", "")).strip()

    payload["texto"] = texto
    payload["keyword"] = keyword
    payload["titulo"] = payload.get("titulo") or _title_from_text(texto)
    payload["meta"] = payload.get("meta") or _meta_from_text(texto)
    payload["slug"] = payload.get("slug") or slugify(keyword)
    return payload


def _verify(
    tarea_seo: Tarea, artefacto: Artefacto, texto_original: str
) -> list[dict]:
    """Ejecuta SEO, estilo y anclaje de hechos sobre el contenido final."""
    payload = tarea_seo.payload
    problemas = verificar_seo(
        titulo=str(payload.get("titulo", "")),
        meta=str(payload.get("meta", "")),
        slug=str(payload.get("slug", "")),
        texto=artefacto.contenido,
        keyword=str(payload.get("keyword", "")),
    )
    problemas.extend(verificar_estilo(artefacto.contenido))

    hechos = anclar_hechos(texto_original, artefacto.contenido)
    if hechos.get("bloquea"):
        problemas.append(
            {
                "regla": hechos["regla"],
                "severidad": hechos["severidad"],
                "mensaje": hechos["mensaje"],
                "sugerencia": hechos["sugerencia"],
                "entidades": hechos.get("entidades", []),
            }
        )
    return problemas


def _move_to_review(tarea: Tarea) -> None:
    """Pasa la tarea principal a revisión.

    ``ejecutar_tarea`` la deja en ``ok``, que es terminal en
    ``Tarea.TRANSICIONES``. Para no tocar los modelos en este paso se actualiza
    el estado directamente; el panel del paso 7 debería formalizar la
    transición ``ok -> revision``.
    """
    Tarea.objects.filter(pk=tarea.pk).update(estado=Tarea.Estado.REVISION)
    tarea.estado = Tarea.Estado.REVISION


def pipeline_editorial(tarea_id: int) -> dict:
    """Reescribe, optimiza y verifica un artículo; devuelve el estado final."""
    tarea = Tarea.objects.filter(pk=tarea_id).first()
    if tarea is None:
        raise ValueError(f"La tarea {tarea_id} no existe.")
    if tarea.estado != Tarea.Estado.COLA:
        raise ValueError(
            f"La tarea {tarea_id} debe estar en cola, no en {tarea.estado}."
        )

    resultado = ejecutar_tarea.call_local(tarea_id)
    tarea.refresh_from_db()
    if resultado != "ok":
        return {
            "estado": tarea.estado,
            "tarea_id": tarea.pk,
            "problemas": [],
            "resultado": resultado,
        }

    artefacto_principal = _latest_artifact(tarea)
    if artefacto_principal is None:
        raise ValueError(f"La tarea {tarea_id} terminó en ok sin artefacto.")

    habilidad_seo = Habilidad.objects.filter(slug="seo").first()
    if habilidad_seo is None:
        raise ValueError("Falta la habilidad con slug 'seo' para el pipeline.")

    tarea_seo = Tarea.objects.create(
        agente=tarea.agente,
        habilidad=habilidad_seo,
        payload=_seo_payload(tarea, artefacto_principal),
    )
    tarea_seo.depende_de.add(tarea)

    resultado_seo = ejecutar_tarea.call_local(tarea_seo.pk)
    tarea_seo.refresh_from_db()
    if resultado_seo != "ok":
        return {
            "estado": tarea.estado,
            "tarea_id": tarea.pk,
            "tarea_seo_id": tarea_seo.pk,
            "problemas": [],
            "resultado": resultado_seo,
        }

    artefacto_final = _latest_artifact(tarea_seo)
    if artefacto_final is None:
        raise ValueError(
            f"La tarea SEO {tarea_seo.pk} terminó en ok sin artefacto."
        )

    texto_original = str(tarea.payload.get("texto", ""))
    problemas = _verify(tarea_seo, artefacto_final, texto_original)
    hay_alta = any(
        problema.get("severidad") == HIGH_SEVERITY for problema in problemas
    )

    metadata = dict(artefacto_final.metadata or {})
    metadata["problemas"] = problemas
    metadata["verificacion"] = "alta" if hay_alta else "ok"
    metadata["tarea_principal"] = tarea.pk
    artefacto_final.metadata = metadata
    artefacto_final.save(update_fields=["metadata"])

    if hay_alta:
        _move_to_review(tarea)
    else:
        tarea.refresh_from_db(fields=["estado"])

    return {
        "estado": tarea.estado,
        "tarea_id": tarea.pk,
        "tarea_seo_id": tarea_seo.pk,
        "artefacto_principal_id": artefacto_principal.pk,
        "artefacto_id": artefacto_final.pk,
        "problemas": problemas,
        "resultado": "ok",
    }
