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
from urllib.parse import quote

import requests
import trafilatura
from bs4 import BeautifulSoup
from django.utils import timezone
from urllib.parse import urljoin
from duckduckgo_search import DDGS

from apps.core.models import (
    Hallazgo,
    InvestigacionProgramada,
    RegistroEjecucionMonitoreo,
)
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


def _extraer_enlaces_de_html(texto_html: str, url_base: str) -> list[dict]:
    """Extrae enlaces válidos de una página HTML de categoría.

    Limpia el DOM eliminando nav/header/footer/aside/script/style,
    prioriza enlaces dentro de contenedores de contenido (main/article/section
    o divs con clases content/post/entry/card/item/list/archive), exige un
    texto visible de al menos 15 caracteres y extrae la fecha de una etiqueta
    <time> en el padre inmediato o ancestro cercano (hasta 3 niveles).

    Retorna una lista de dicts:
        [{"url": url_absoluta, "title": texto_visible, "fecha": iso_o_vacío}]
    """
    if not texto_html or not texto_html.strip():
        return []
    soup = BeautifulSoup(texto_html, "html.parser")

    # a) Limpieza del DOM: eliminar contenedores de navegación y elementos
    #    no relevantes antes de extraer enlaces.
    for elemento in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        elemento.decompose()

    extensiones_ignoradas = (".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".pdf")
    enlaces: list[dict] = []
    enlaces_encontrados: set[str] = set()

    def _es_recurso_estatico(href: str) -> bool:
        return href.lower().endswith(extensiones_ignoradas)

    def _fecha_de_ancestro(anchor) -> str:
        """Busca <time> en el padre inmediato o ancestro cercano (hasta 3 niveles)."""
        nodo = anchor.parent
        for _ in range(3):
            if nodo is None:
                break
            time_tag = nodo.find("time")
            if time_tag:
                return time_tag.get("datetime") or time_tag.get("content") or ""
            nodo = nodo.parent
        return ""

    def _procesar_anchor(anchor) -> None:
        href = anchor.get("href", "").strip()
        if not href:
            return
        if href.startswith("#") or href.startswith("mailto:"):
            return
        if _es_recurso_estatico(href):
            return
        # c) Filtro de texto: exigir al menos 15 caracteres visibles.
        texto = anchor.get_text(strip=True)
        if len(texto) < 15:
            return
        url_absoluta = urljoin(url_base, href)
        if url_absoluta in enlaces_encontrados:
            return
        enlaces_encontrados.add(url_absoluta)
        enlaces.append(
            {
                "url": url_absoluta,
                "title": texto,
                "fecha": _fecha_de_ancestro(anchor),
            }
        )

    # b) Priorización de contenedores: buscar enlaces dentro de main/article/
    #    section o divs con clases relacionadas con contenido.
    contenedores = []
    for etiqueta in ["main", "article", "section"]:
        contenedores.extend(soup.find_all(etiqueta))
    for div in soup.find_all("div"):
        clases = div.get("class", [])
        clases_texto = " ".join(clases).lower() if isinstance(clases, list) else ""
        if any(
            palabra in clases_texto
            for palabra in ("content", "post", "entry", "card", "item", "list", "archive")
        ):
            contenedores.append(div)

    for contenedor in contenedores:
        for anchor in contenedor.find_all("a", href=True):
            _procesar_anchor(anchor)

    # d) Fallback: si no se encontraron contenedores claros, extraer todos los
    #    <a> restantes filtrando agresivamente hrefs de navegación.
    if not enlaces:
        for anchor in soup.find_all("a", href=True):
            href_lower = anchor.get("href", "").lower()
            if any(
                palabra in href_lower
                for palabra in ("menu", "nav", "login", "register")
            ):
                continue
            _procesar_anchor(anchor)

    return enlaces


def _buscar_con_duckduckgo(consulta: str, max_resultados: int = 10) -> tuple[list[dict], str | None]:
    """Busca por palabra clave en DuckDuckGo sin API key.

    Retorna (lista_resultados, mensaje_error).
    Best-effort: si la búsqueda falla, retorna lista vacía y el mensaje de error
    para que el llamante lo registre como un fallo visible.
    """
    try:
        resultados = DDGS().text(consulta, max_results=max_resultados)
        return (
            [
                {
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "resumen": r.get("body", ""),
                    "fecha": r.get("date", ""),
                }
                for r in resultados or []
            ],
            None,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort, nunca aborta
        logger.warning("Fallo de búsqueda DuckDuckGo para %s: %s", consulta, exc)
        return [], f"Error de búsqueda DuckDuckGo: {exc}"


def _construir_url_google_news(consulta: str) -> str:
    """Construye la URL del feed RSS de Google News para una consulta."""
    consulta_codificada = quote(consulta, safe="")
    return (
        f"https://news.google.com/rss/search?q={consulta_codificada}"
        f"&hl=es-419&gl=VE&ceid=VE:es-419&tbs=qdr:w"
    )


def _construir_urls_a_procesar(investigacion: InvestigacionProgramada) -> tuple[list[str], str | None]:
    """Construye la lista de URLs a procesar según el modo de búsqueda.

    - sitio: usa urls_objetivo línea por línea (comportamiento existente).
    - busqueda: busca en DuckDuckGo y usa las URLs encontradas.
    - noticias: construye la URL de Google News RSS para la consulta.

    Retorna (urls, mensaje_error). Si hay error de búsqueda, urls es [] y
    mensaje_error describe el fallo.
    """
    modo = investigacion.modo_busqueda or InvestigacionProgramada.MODO_SITIO

    if modo == InvestigacionProgramada.MODO_BUSQUEDA:
        consulta = investigacion.consulta_busqueda or ""
        if not consulta.strip():
            return [], None
        resultados, error_busqueda = _buscar_con_duckduckgo(
            consulta, investigacion.limite_por_fuente
        )
        if error_busqueda:
            return [], error_busqueda
        return [r["url"] for r in resultados if r.get("url")], None

    if modo == InvestigacionProgramada.MODO_NOTICIAS:
        consulta = investigacion.consulta_busqueda or ""
        if not consulta.strip():
            return [], None
        return [_construir_url_google_news(consulta)], None

    # Modo sitio (default): URLs objetivo línea por línea.
    return [
        u.strip() for u in (investigacion.urls_objetivo or "").splitlines() if u.strip()
    ], None


def ejecutar_investigacion(investigacion: InvestigacionProgramada) -> dict:
    """Ejecuta una investigación programada de forma síncrona.

    Descarga cada URL no vacía de urls_objetivo (o URLs de búsqueda según el
    modo), valida SSRF antes de cada petición, detecta el tipo, parsea y
    guarda hallazgos sin duplicar.

    Retorna un dict con conteos:
        {
            "ejecutadas": n,
            "hallazgos_nuevos": m,
            "filtrados": k,
            "fallos": [{"url": ..., "error": ...}, ...]
        }

    Nunca lanza excepciones por errores de red de una URL: las captura,
    registra en fallos y continúa con la siguiente.
    """
    registro = RegistroEjecucionMonitoreo.objects.create(
        investigacion=investigacion,
        inicio=timezone.now(),
        estado="parcial",
    )

    ejecutadas = 0
    hallazgos_nuevos = 0
    filtrados = 0
    fallos = []

    urls_a_procesar, error_urls = _construir_urls_a_procesar(investigacion)

    if error_urls:
        fallos.append(
            {
                "url": f"búsqueda: {investigacion.consulta_busqueda}",
                "error": error_urls,
            }
        )
        # Fallo en la etapa de descubrimiento: registrar como fallido,
        # no tocar ultima_ejecucion para evitar desplazamiento horario.
        registro.estado = "fallido"
        registro.fin = timezone.now()
        registro.fallos_detalle = fallos
        registro.save(update_fields=["estado", "fin", "fallos_detalle"])
        return {
            "ejecutadas": ejecutadas,
            "hallazgos_nuevos": hallazgos_nuevos,
            "filtrados": filtrados,
            "fallos": fallos,
        }

    else:
        for url in urls_a_procesar:
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

            if response.status_code < 200 or response.status_code >= 300:
                fallos.append(
                    {"url": url, "error": f"HTTP {response.status_code} al descargar la URL."}
                )
                continue

            texto_html = response.text
            tipo = _detectar_tipo(texto_html)

            # Obtener la lista de artículos candidatos y el tipo de fuente.
            if tipo == "sitemap":
                entradas = _parsear_sitemap(texto_html)
                if entradas and "error" in entradas[0]:
                    fallos.append({"url": url, "error": entradas[0]["error"]})
                    continue
                items = [
                    {
                        "url": e.get("url") or "",
                        "title": e.get("title", ""),
                        "fecha_publicacion": e.get("lastmod") or "",
                        "resumen": "",
                    }
                    for e in entradas[: investigacion.limite_por_fuente]
                ]
                tipo_fuente = Hallazgo.TipoFuente.SITEMAP
            elif tipo == "rss":
                items_rss = _parsear_rss(texto_html)
                if items_rss and "error" in items_rss[0]:
                    fallos.append({"url": url, "error": items_rss[0]["error"]})
                    continue
                items = [
                    {
                        "url": i.get("link") or "",
                        "title": i.get("title", ""),
                        "fecha_publicacion": i.get("pubDate") or "",
                        "resumen": i.get("description") or "",
                    }
                    for i in items_rss[: investigacion.limite_por_fuente]
                ]
                tipo_fuente = Hallazgo.TipoFuente.RSS
            else:
                # Página HTML de categoría: extraer enlaces y procesarlos como artículos.
                # NOTA: Los href extraídos no se re-validan con SSRF, consistente con el
                # comportamiento de RSS/Sitemap. Documentado en HTML-SCRAPER-01.
                items = [
                    {
                        "url": it.get("url") or "",
                        "title": it.get("title", ""),
                        "fecha_publicacion": it.get("fecha", ""),
                        "resumen": "",
                    }
                    for it in _extraer_enlaces_de_html(texto_html, url)
                ][: investigacion.limite_por_fuente]
                tipo_fuente = "html"

            # Bucle común de filtrado por palabras clave y guardado como Hallazgo.
            for item in items:
                url_articulo = item.get("url") or ""
                if not url_articulo:
                    continue
                texto_a_evaluar = f"{item.get('title', '')} {url_articulo}"
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
                        "tipo_fuente": tipo_fuente,
                        "titulo": item.get("title") or "",
                        "fecha_publicacion": item.get("fecha_publicacion", ""),
                        "resumen": item.get("resumen", ""),
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

    # Al final de una ejecución exitosa o parcial.
    fin = timezone.now()
    estado = "exitoso" if not fallos else "parcial"
    registro.fin = fin
    registro.estado = estado
    registro.hallazgos_nuevos = hallazgos_nuevos
    registro.filtrados = filtrados
    registro.fallos_detalle = fallos
    registro.save(
        update_fields=["fin", "estado", "hallazgos_nuevos", "filtrados", "fallos_detalle"]
    )

    # Guarda la hora de INICIO (no el fin) para evitar el desplazamiento
    # acumulativo: el siguiente vencimiento se calcula desde la hora programada
    # de esta ejecución, independientemente de cuánto tardó en completarse.
    investigacion.ultima_ejecucion = registro.inicio
    investigacion.save(update_fields=["ultima_ejecucion"])

    return {
        "ejecutadas": ejecutadas,
        "hallazgos_nuevos": hallazgos_nuevos,
        "filtrados": filtrados,
        "fallos": fallos,
    }
