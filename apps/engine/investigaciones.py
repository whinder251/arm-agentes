"""Servicio de ejecución de investigaciones programadas.

Descarga las URLs objetivo de una InvestigacionProgramada, detecta si cada
una es un feed RSS o un sitemap, la parsea reutilizando los parsers de
apps.engine.tool_executor y guarda cada artículo/entrada como un Hallazgo.

El módulo es resiliente: un fallo de red en una URL no aborta el procesamiento
de las demás y no lanza excepciones que afecten al registro de la investigación.
"""

import logging
import random
import time
import xml.etree.ElementTree as ET

import requests
import trafilatura
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

# Códigos de HTTP que se respetan sin reintentar (no somos insistentes).
CODIGOS_NO_REINTENTAR = {429, 503, 403}

# Límite duro de caracteres por artículo extraído.
LIMITE_CARACTERES_CONTENIDO = 8000


def _coincide_con_palabras_clave(texto: str, palabras_clave: str) -> bool:
    """Devuelve True si el texto contiene alguna de las palabras clave.

    La comparación es insensible a mayúsculas. Si no hay palabras clave
    definidas, devuelve True (comportamiento retrocompatible: guarda todo).
    """
    if not palabras_clave:
        return True
    texto_lower = texto.lower()
    claves = [k.strip().lower() for k in palabras_clave.split(",") if k.strip()]
    return any(clave in texto_lower for clave in claves)


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


# NOTA: Crawl4AI eliminado; la cascada ahora tiene 2 niveles (Trafilatura -> Jina AI).


def _extraer_contenido(url: str) -> str:
    """Descarga la URL y extrae el texto principal con cascada de 2 niveles.

    Nivel 1: trafilatura sobre el HTML descargado.
    Nivel 2: Jina AI (https://r.jina.ai/{url}) si trafilatura falla.

    Best-effort: cualquier error de red, HTTP 429/503/403, HTML vacío o
    fallo de ambos niveles devuelve cadena vacía sin lanzar excepción,
    para que un artículo que no carga nunca aborte la investigación completa.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEGUNDOS,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        logger.warning("Error de red extrayendo contenido de %s: %s", url, exc)
        return ""
    if response.status_code in CODIGOS_NO_REINTENTAR:
        logger.warning(
            "HTTP %s extrayendo contenido de %s, sin reintento",
            response.status_code,
            url,
        )
        return ""
    html = response.text or ""
    if not html.strip():
        logger.warning("HTML vacío extrayendo contenido de %s", url)
        return ""

    # Nivel 1: Trafilatura sobre el HTML descargado.
    try:
        texto = trafilatura.extract(html)
    except Exception as exc:  # noqa: BLE001 - best-effort, nunca aborta
        logger.warning("Fallo de trafilatura extrayendo %s: %s", url, exc)
        texto = None
    if texto and texto.strip():
        return texto[:LIMITE_CARACTERES_CONTENIDO]

    # Nivel 2: Jina AI como fallback.
    try:
        jina_url = f"https://r.jina.ai/{url}"
        jina_response = requests.get(
            jina_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SEGUNDOS,
            allow_redirects=True,
        )
        if jina_response.status_code == 200 and jina_response.text.strip():
            logger.info(
                "Contenido extraído exitosamente con Jina AI para %s", url
            )
            return jina_response.text[:LIMITE_CARACTERES_CONTENIDO]
    except requests.RequestException as exc:
        logger.warning("Fallo del fallback Jina AI para %s: %s", url, exc)

    # Si los 2 niveles fallan.
    logger.warning("No se pudo extraer contenido de %s tras 2 intentos", url)
    return ""


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
    filtrados = 0
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
                texto_a_evaluar = f"{entrada.get('title', '')} {url_articulo}"
                if not _coincide_con_palabras_clave(
                    texto_a_evaluar, investigacion.palabras_clave
                ):
                    filtrados += 1
                    continue  # Descartar el artículo, no guardar como Hallazgo
                hallazgo, creado = Hallazgo.objects.update_or_create(
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
                    if url_articulo:
                        time.sleep(random.uniform(1.0, 2.5))
                        contenido = _extraer_contenido(url_articulo)
                        if contenido:
                            hallazgo.contenido_extraido = contenido
                            hallazgo.save(update_fields=["contenido_extraido"])
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
                texto_a_evaluar = f"{item.get('title', '')} {item.get('description', '')}"
                if not _coincide_con_palabras_clave(
                    texto_a_evaluar, investigacion.palabras_clave
                ):
                    filtrados += 1
                    continue  # Descartar el artículo, no guardar como Hallazgo
                hallazgo, creado = Hallazgo.objects.update_or_create(
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
                    if url_articulo:
                        time.sleep(random.uniform(1.0, 2.5))
                        contenido = _extraer_contenido(url_articulo)
                        if contenido:
                            hallazgo.contenido_extraido = contenido
                            hallazgo.save(update_fields=["contenido_extraido"])
                    hallazgos_nuevos += 1

    # Actualizar última ejecución fuera de cualquier transacción abierta
    # durante llamadas de red (seguridad.md §9: no mantener transacciones abiertas).
    investigacion.ultima_ejecucion = timezone.now()
    investigacion.save(update_fields=["ultima_ejecucion"])

    return {
        "ejecutadas": ejecutadas,
        "hallazgos_nuevos": hallazgos_nuevos,
        "filtrados": filtrados,
        "fallos": fallos,
    }
