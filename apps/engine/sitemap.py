"""Generación de sitemap XML para tareas completadas."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable

from django.conf import settings

from apps.core.models import Tarea


def generar_sitemap(tareas_ok: Iterable[Tarea], base_url: str | None = None) -> str:
    """Genera un string XML válido con la estructura <urlset> de sitemap.

    Incluye la URL de cada tarea y la fecha de última modificación (actualizado_en).
    """
    if base_url is None:
        base_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
    base_url = base_url.rstrip("/")

    root = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    for tarea in tareas_ok:
        url_elem = ET.SubElement(root, "url")

        slug = None
        if tarea.payload:
            slug = tarea.payload.get("slug")
        if not slug and tarea.artefactos.exists():
            latest = tarea.artefactos.order_by("-version").first()
            if latest and latest.metadata:
                slug = latest.metadata.get("slug")

        path = f"/{slug}/" if slug else f"/{tarea.pk}/"
        loc = f"{base_url}{path}"

        loc_elem = ET.SubElement(url_elem, "loc")
        loc_elem.text = loc

        if hasattr(tarea, "actualizado_en") and tarea.actualizado_en:
            lastmod_elem = ET.SubElement(url_elem, "lastmod")
            lastmod_elem.text = tarea.actualizado_en.strftime("%Y-%m-%d")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
