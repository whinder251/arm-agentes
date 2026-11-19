"""Servicio de ejecución de investigaciones programadas.

Descarga las URLs objetivo de una InvestigacionProgramada, detecta si cada
una es un feed RSS o un sitemap, la parsea reutilizando los parsers de
apps.engine.tool_executor y guarda cada artículo/entrada como un Hallazgo.

El módulo es resiliente: un fallo de red en una URL no aborta el procesamiento
de las demás y no lanza excepciones que afecten al registro de la investigación.
"""

import logging
import xml.etree.ElementTree as ET

import requests
from django.utils import timezone

from apps.core.models import Hallazgo, InvestigacionProgramada
from apps.engine.tool_executor import (
    _parsear_rss,
    _parsear_sitemap,
    _validar_endpoint_seguro,
)

logger = logging.getLogger(__name__)

# User-Agent de navegador real: los WAF (SiteGround/sgcaptcha, Cloudflare)
# bloquean los User-Agent de script al descargar sitemaps y feeds.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIMEOUT_SEGUNDOS = 15


def _detectar_tipo(texto_xml: str) -> str:
    """Detecta el tipo de fuente a partir del texto XML.

    Reutiliza la lógica de tool_executor: lee el tag raíz sin namespace.
    Retorna "rss", "sitemap" o "desconocido".
    """
    if not texto_xml or not texto_xml.strip():
        return "desconocido"
    try:
        raiz = ET.fromstring(texto_xml.strip())
    except Exception:
        return "desconocido"
    tag = raiz.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    if tag in ("urlset", "sitemapindex"):
        return "sitemap"
    if tag in ("rss", "feed", "rdf:RDF"):
        return "rss"
    return "desconocido"


def ejecutar_investigacion(investigacion: InvestigacionProgramada) -> dict:
    """Ejecuta una investigación programada de forma síncrona.

    Descarga cada URL no vacía de urls_objetivo, valida SSRF antes de cada
    petición, detecta el tipo, parsea y guarda hallazgos sin duplicar.

    Retorna un dict con conteos:
        {
            "ejecutadas": n,
            "hallazgos_nuevos": m,
            "fallos": [{"url": ..., "error": ...}, ...]
        }

    Nunca lanza excepciones por errores de red de una URL: las captura,
    registra en fallos y continúa con la siguiente.
    """
    ejecutadas = 0
    hallazgos_nuevos = 0
    fallos = []

    urls = [u.strip() for u in (investigacion.urls_objetivo or "").splitlines() if u.strip()]

    for url in urls:
        # Validar SSRF antes de cada petición (seguridad.md §5).
        try:
            _validar_endpoint_seguro(url)
        except ValueError as exc:
            fallos.append({"url": url, "error": str(exc)})
            continue

        # Descarga con timeout siguiendo redirecciones (necesario para muchos feeds).
        # La validación SSRF ya se ejecutó sobre la URL original.
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT_SEGUNDOS,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            fallos.append({"url": url, "error": f"Error de red: {exc}"})
            logger.warning(
                "Error de red descargando URL de investigación %s: %s - %s",
                investigacion.pk,
                url,
                exc,
            )
            continue

        ejecutadas += 1

        if response.status_code != 200:
            fallos.append(
                {"url": url, "error": f"HTTP {response.status_code} al descargar la URL."}
            )
            continue

        texto_xml = response.text
        tipo = _detectar_tipo(texto_xml)

        if tipo == "desconocido":
            fallos.append({"url": url, "error": "No se pudo detectar el tipo de fuente (RSS o Sitemap)."})
            continue

        # Parsear reutilizando los parsers existentes de tool_executor.
        if tipo == "sitemap":
            entradas = _parsear_sitemap(texto_xml)
            if entradas and "error" in entradas[0]:
                fallos.append({"url": url, "error": entradas[0]["error"]})
                continue
            for entrada in entradas:
                url_articulo = entrada.get("url") or ""
                if not url_articulo:
                    continue
                _, creado = Hallazgo.objects.update_or_create(
                    investigacion=investigacion,
                    url_articulo=url_articulo,
                    defaults={
                        "url_fuente": url,
                        "tipo_fuente": Hallazgo.TipoFuente.SITEMAP,
                        "titulo": "",
                        "fecha_publicacion": entrada.get("lastmod") or "",
                        "resumen": "",
                    },
                )
                if creado:
                    hallazgos_nuevos += 1
        else:  # rss
            items = _parsear_rss(texto_xml)
            if items and "error" in items[0]:
                fallos.append({"url": url, "error": items[0]["error"]})
                continue
            for item in items:
                url_articulo = item.get("link") or ""
                if not url_articulo:
                    continue
                _, creado = Hallazgo.objects.update_or_create(
                    investigacion=investigacion,
                    url_articulo=url_articulo,
                    defaults={
                        "url_fuente": url,
                        "tipo_fuente": Hallazgo.TipoFuente.RSS,
                        "titulo": item.get("title") or "",
                        "fecha_publicacion": item.get("pubDate") or "",
                        "resumen": item.get("description") or "",
                    },
                )
                if creado:
                    hallazgos_nuevos += 1

    # Actualizar última ejecución fuera de cualquier transacción abierta
    # durante llamadas de red (seguridad.md §9: no mantener transacciones abiertas).
    investigacion.ultima_ejecucion = timezone.now()
    investigacion.save(update_fields=["ultima_ejecucion"])

    return {
        "ejecutadas": ejecutadas,
        "hallazgos_nuevos": hallazgos_nuevos,
        "fallos": fallos,
    }
