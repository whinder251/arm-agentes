"""Infraestructura de ejecución segura de herramientas.

Este módulo provee funciones para resolver e inyectar credenciales
desencriptadas en tiempo de ejecución, con validación SSRF, timeout
obligatorio y sanitizado de logs. Listo para ser consumido por el
orquestador (Fase 4) y por el botón "Probar conexión" del panel.
"""

import base64
import json
import logging
import re
import socket
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import ipaddress
import requests

from apps.core.models import Credencial, Herramienta

logger = logging.getLogger(__name__)

# Excepción personalizada para errores de ejecución de herramientas
class ToolExecutionError(Exception):
    """Error genérico de ejecución de herramienta sin filtrar detalles sensibles."""
    pass


# Claves que nunca deben aparecer en logs ni serializaciones (case-insensitive)
_CLAVES_SENSIBLES = {
    "api_key",
    "apikey",
    "secret",
    "secreto",
    "password",
    "token",
    "authorization",
    "cookie",
    "secreto_desencriptado",
    "credentials_json",
    "app_password",
    "x-api-key",
    "x_api_key",
}


# Headers que no pueden ser sobrescritos por extra_headers
_HEADERS_PROTEGIDOS = {
    "authorization",
    "host",
    "content-length",
    "connection",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-forwarded-port",
    "forwarded",
}


def _sanitizar_config(config: dict) -> dict:
    """Devuelve una copia profunda del diccionario con claves sensibles enmascaradas.

    Sanitiza recursivamente diccionarios anidados (ej. headers, metadata, params)
    verificando el NOMBRE de la clave (case-insensitive) en TODOS los niveles.
    """

    def _sanitizar_valor(valor: Any) -> Any:
        if isinstance(valor, dict):
            sanitizado = {}
            for clave, subvalor in valor.items():
                if isinstance(clave, str) and clave.lower() in _CLAVES_SENSIBLES:
                    sanitizado[clave] = "***"
                else:
                    sanitizado[clave] = _sanitizar_valor(subvalor)
            return sanitizado
        elif isinstance(valor, list):
            return [_sanitizar_valor(v) for v in valor]
        return valor

    return _sanitizar_valor(config)


def _validar_endpoint_seguro(url: str) -> None:
    """Valida que el endpoint no apunte a redes internas (SSRF).

    Usa ipaddress para verificar que la IP resuelta sea is_global.
    Rechaza explícitamente IPs privadas, loopback, link-local, multicast,
    reservadas y desempaqueta direcciones IPv4-mapped en IPv6.

    Lanza ValueError si la URL resuelve a una IP bloqueada.
    """
    if not url:
        raise ValueError("Endpoint vacío: no se puede validar.")

    partes = urlparse(url)
    if not partes.hostname:
        raise ValueError("URL sin hostname válido.")

    hostname = partes.hostname

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(f"No se pudo resolver el hostname '{hostname}': {exc}")

    for familia, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            direccion = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        # Desempaquetar IPv4-mapped IPv6 (ej. ::ffff:127.0.0.1 → 127.0.0.1)
        if direccion.version == 6 and direccion.ipv4_mapped:
            direccion = direccion.ipv4_mapped

        # Validar usando is_global (True solo para IPs públicas globales)
        # is_global es False para: private, loopback, link-local, multicast, reserved, unspecified
        if not direccion.is_global:
            raise ValueError(
                f"Endpoint bloqueado por política SSRF: {ip_str} "
                f"no es una IP pública global (pertenece a rango restringido)."
            )


def _resolver_placeholders(config: dict, secreto: str) -> dict:
    """Recorre recursivamente el diccionario y reemplaza {{secreto}} con el valor real.

    Maneja dicts anidados, listas y strings. Solo reemplaza la cadena exacta
    "{{secreto}}" (case-sensitive) para evitar falsos positivos.
    """

    def _resolver_valor(valor: Any) -> Any:
        if isinstance(valor, str):
            return valor.replace("{{secreto}}", secreto)
        elif isinstance(valor, dict):
            return {clave: _resolver_valor(subvalor) for clave, subvalor in valor.items()}
        elif isinstance(valor, list):
            return [_resolver_valor(item) for item in valor]
        return valor

    return _resolver_valor(config)


def _obtener_configuracion_ejecucion(herramienta: Herramienta) -> dict:
    """Fusiona la configuración de la herramienta con su credencial desencriptada.

    Prioridad de fusión (de menor a mayor precedencia):
    1. metadata de la credencial (base_url, username, header_scheme, etc.)
    2. configuración propia de la herramienta (endpoint, timeout, params)
    3. secreto_desencriptado (inyectado al final)

    IMPORTANTE: El `base_url` de destino DEBE provenir de `credencial.metadata`
    para prevenir cross-wiring (host malicioso). El `endpoint` (ruta) puede venir
    de la herramienta. Se ignora `base_url` en `herramienta.configuracion`.

    Lanza ValueError si la credencial existe pero su secreto está vacío.
    """
    # Tomar configuración de la herramienta, PERO eliminar base_url (solo de credencial)
    config_herramienta = dict(herramienta.configuracion or {})
    # Eliminar base_url de la herramienta - SOLO credencial define el host
    config_herramienta.pop("base_url", None)
    # endpoint se conserva: la herramienta define la ruta

    if herramienta.credencial is not None:
        credencial: Credencial = herramienta.credencial
        secreto = credencial.secreto_cifrado  # Django lo desencripta automáticamente
        metadata = credencial.metadata or {}

        if not secreto:
            raise ValueError(
                f"La credencial '{credencial.nombre}' (slug: {credencial.slug}) "
                f"está vinculada a la herramienta '{herramienta.nombre}' "
                f"pero su secreto está vacío."
            )

        # Resolver placeholders {{secreto}} en metadata ANTES de fusionar
        metadata = _resolver_placeholders(metadata, secreto)

        # Fusionar: metadata < config_herramienta < secreto
        # metadata provee base_url (OBLIGATORIO), header_scheme, header_name, username, etc.
        # config_herramienta provee endpoint, timeout, params, etc.
        config_ejecucion = {**metadata, **config_herramienta}
        config_ejecucion["secreto_desencriptado"] = secreto
        return config_ejecucion

    return config_herramienta


def _construir_headers_autenticacion(config: dict) -> dict:
    """Construye los headers de autenticación según el tipo de credencial.

    Respeta `Credencial.tipo` (vía metadata header_scheme):
    - api_key: usa `header_name` (default 'X-API-Key')
    - basic: usa `username` del metadata y codifica en Base64
    - bearer: usa el secreto en Authorization: Bearer
    - json: no añade headers, solo marca para inyección en body
    """
    headers = {}
    secreto = config.get("secreto_desencriptado")
    if not secreto:
        return headers

    header_scheme = config.get("header_scheme", "bearer").lower()

    if header_scheme == "bearer":
        headers["Authorization"] = f"Bearer {secreto}"
    elif header_scheme == "api_key":
        header_name = config.get("header_name", "X-API-Key")
        headers[header_name] = secreto
    elif header_scheme == "basic":
        username = config.get("username", "")
        token = base64.b64encode(f"{username}:{secreto}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    # Para 'json' el secreto va en el body, no en headers

    return headers


_NAMESPACE_SITEMAP = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _parsear_sitemap(xml_text: str) -> list[dict]:
    """Parsea un sitemap.xml y devuelve una lista de diccionarios con url, lastmod y priority.

    Si el XML es inválido, está vacío o no tiene estructura de sitemap,
    devuelve [{"error": "..."}] sin lanzar excepción.
    """
    if not xml_text or not xml_text.strip():
        return [{"error": "No es un sitemap.xml válido o la estructura es inesperada"}]

    try:
        raiz = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return [{"error": "No es un sitemap.xml válido o la estructura es inesperada"}]

    # Quitar namespaces para buscar etiquetas sin prefijo (más robusto ante variantes)
    for elem in raiz.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    urls = []
    for url_elem in raiz.findall("url"):
        loc_elem = url_elem.find("loc")
        lastmod_elem = url_elem.find("lastmod")
        priority_elem = url_elem.find("priority")
        changefreq_elem = url_elem.find("changefreq")

        urls.append({
            "url": (loc_elem.text.strip() if loc_elem is not None and loc_elem.text else ""),
            "lastmod": (lastmod_elem.text.strip() if lastmod_elem is not None and lastmod_elem.text else ""),
            "priority": (priority_elem.text.strip() if priority_elem is not None and priority_elem.text else ""),
            "changefreq": (changefreq_elem.text.strip() if changefreq_elem is not None and changefreq_elem.text else ""),
        })

    if not urls:
        return [{"error": "No es un sitemap.xml válido o la estructura es inesperada"}]

    return urls


# Stopwords español/inglés para filtrar en el cálculo de densidad de palabras clave.
_STOPWORDS_ES_EN = {
    # español
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "pero", "aunque",
    "si", "no", "que", "de", "del", "en", "por", "para", "con", "sin", "sobre",
    "entre", "desde", "hasta", "como", "más", "menos", "muy", "mejor", "peor",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas", "aquel", "aquella",
    "aquello", "es", "son", "era", "eras", "eramos", "eran", "ser", "estar", "estoy",
    "estás", "está", "estamos", "estáis", "están", "he", "has", "ha", "hemos", "habéis",
    "han", "tengo", "tienes", "tiene", "tenemos", "tenéis", "tienen", "al", "lo", "le",
    "les", "me", "te", "se", "nos", "os", "mi", "tu", "su", "mis", "tus", "sus", "uno",
    "cual", "quien", "quienes", "donde", "cuando", "porque", "ya", "todavia", "aun",
    # inglés
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "at", "from",
    "by", "for", "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "of", "in", "on", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "don",
    "should", "now", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "having", "do", "does", "did", "doing", "will", "would", "could", "should",
    "may", "might", "must", "shall", "can", "need", "i", "me", "my", "myself", "we",
    "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves", "he",
    "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom",
    "this", "that", "these", "those", "am",
}


class _SEOParser(HTMLParser):
    """Parser ligero (stdlib html.parser) que extrae la estructura SEO de un HTML."""

    def __init__(self, url_base: str):
        super().__init__()
        self.url_base = url_base or ""
        self.dominio_base = urlparse(self.url_base).netloc.lower() if self.url_base else ""
        self.title = ""
        self._en_title = False
        self.meta_description = ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.h3: list[str] = []
        self._heading_tag: str | None = None
        self._heading_text: list[str] = []
        self.body_text: list[str] = []
        self._en_body = False
        self.internal_links = 0
        self.external_links = 0
        self.images_sin_alt = 0
        self.schema_types: list[str] = []
        self._en_script_ldjson = False
        self._script_ldjson_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k: (v or "") for k, v in attrs}
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._en_title = True
        elif tag_lower == "meta":
            nombre = attrs_dict.get("name", "").lower()
            if nombre == "description":
                self.meta_description = attrs_dict.get("content", "")
        elif tag_lower in ("h1", "h2", "h3"):
            self._heading_tag = tag_lower
            self._heading_text = []
        elif tag_lower == "body":
            self._en_body = True
        elif tag_lower == "a":
            href = attrs_dict.get("href", "")
            if href:
                href_absoluto = urljoin(self.url_base or "https://x.invalid/", href)
                dominio_href = urlparse(href_absoluto).netloc.lower()
                if dominio_href and dominio_href == self.dominio_base:
                    self.internal_links += 1
                else:
                    self.external_links += 1
        elif tag_lower == "img":
            if "alt" not in attrs_dict:
                self.images_sin_alt += 1
        elif tag_lower == "script":
            if attrs_dict.get("type", "") == "application/ld+json":
                self._en_script_ldjson = True
                self._script_ldjson_text = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._en_title = False
        elif tag_lower in ("h1", "h2", "h3") and self._heading_tag == tag_lower:
            texto = "".join(self._heading_text).strip()
            if texto:
                getattr(self, tag_lower).append(texto)
            self._heading_tag = None
            self._heading_text = []
        elif tag_lower == "body":
            self._en_body = False
        elif tag_lower == "script" and self._en_script_ldjson:
            self._en_script_ldjson = False
            texto = "".join(self._script_ldjson_text).strip()
            if texto:
                try:
                    datos = json.loads(texto)
                    self.schema_types.extend(self._extraer_tipos_schema(datos))
                except Exception:
                    self.schema_types.append("desconocido")
            self._script_ldjson_text = []

    def handle_data(self, data: str) -> None:
        if self._en_title:
            self.title += data
        if self._heading_tag:
            self._heading_text.append(data)
        if self._en_body:
            self.body_text.append(data)
        if self._en_script_ldjson:
            self._script_ldjson_text.append(data)

    @staticmethod
    def _extraer_tipos_schema(datos: Any) -> list[str]:
        """Extrae valores de @type de un objeto JSON-LD (dict o lista anidada)."""
        tipos: list[str] = []
        if isinstance(datos, dict):
            t = datos.get("@type")
            if t is not None:
                if isinstance(t, list):
                    tipos.extend(str(x) for x in t)
                else:
                    tipos.append(str(t))
        elif isinstance(datos, list):
            for item in datos:
                tipos.extend(_SEOParser._extraer_tipos_schema(item))
        return tipos


def _analizar_seo_on_page(html: str, url_base: str) -> dict:
    """Extrae la estructura SEO completa de un HTML.

    Devuelve siempre un dict con los campos esperados; en caso de HTML
    vacío o error de parseo, devuelve campos vacíos y un mensaje en 'error'.
    Nunca lanza excepciones que rompan el flujo del llamador.
    """
    vacio = {
        "error": "",
        "title": "",
        "meta_description": "",
        "h1": [],
        "h2": [],
        "h3": [],
        "word_count": 0,
        "keyword_density": [],
        "internal_links": 0,
        "external_links": 0,
        "images_sin_alt": 0,
        "schema_markup": [],
    }

    if not html or not html.strip():
        vacio["error"] = "HTML vacío o nulo"
        return vacio

    try:
        parser = _SEOParser(url_base)
        parser.feed(html)
        parser.close()
    except Exception as exc:  # HTML muy roto: no romper el flujo
        vacio["error"] = f"Error parseando HTML: {exc}"
        return vacio

    # Title recortado a 60 caracteres
    title = parser.title.strip()
    if len(title) > 60:
        title = title[:57].strip() + "..."

    # Conteo de palabras del cuerpo (sin tags)
    texto_body = " ".join(parser.body_text)
    palabras = re.findall(r"\w+", texto_body, flags=re.UNICODE)
    word_count = len(palabras)

    # Densidad de palabras clave (top 10, sin stopwords)
    palabras_filtradas = [p.lower() for p in palabras if p.lower() not in _STOPWORDS_ES_EN]
    contador = Counter(palabras_filtradas)
    total = len(palabras_filtradas)
    keyword_density = []
    for palabra, conta in contador.most_common(10):
        porcentaje = round((conta / total) * 100, 2) if total else 0
        keyword_density.append({"palabra": palabra, "conteo": conta, "porcentaje": porcentaje})

    return {
        "error": "",
        "title": title,
        "meta_description": parser.meta_description.strip(),
        "h1": parser.h1,
        "h2": parser.h2,
        "h3": parser.h3,
        "word_count": word_count,
        "keyword_density": keyword_density,
        "internal_links": parser.internal_links,
        "external_links": parser.external_links,
        "images_sin_alt": parser.images_sin_alt,
        "schema_markup": parser.schema_types,
    }


def _ejecutar_herramienta_http(herramienta: Herramienta, payload: dict) -> dict:
    """Ejecuta una petición HTTP usando la herramienta y su credencial.

    Args:
        herramienta: Instancia de Herramienta con credencial opcional.
        payload: Diccionario con el cuerpo de la petición.

    Returns:
        Diccionario con 'status' (int) y 'body' (dict o str).

    Lanza:
        ValueError: Si falla la validación SSRF o validación de inputs.
        ToolExecutionError: Errores de red/HTTP envueltos sin filtrar detalles sensibles.
    """
    config = _obtener_configuracion_ejecucion(herramienta)

    # Determinar endpoint: primero de la configuracion de la herramienta,
    # y como fallback del payload (util para herramientas sin credencial como
    # sitemap-reader y seo-analyzer que reciben la URL absoluta en la llamada).
    endpoint = config.get("endpoint") or payload.get("endpoint")
    base_url = config.get("base_url")

    if not endpoint:
        raise ValueError(
            f"La herramienta '{herramienta.nombre}' no tiene 'endpoint' configurado."
        )

    if endpoint.startswith(("http://", "https://")):
        # URL absoluta: se usa directamente (herramientas sin credencial como sitemap-reader)
        url_final = endpoint
    else:
        # Ruta relativa: exige base_url de la credencial (anti cross-wiring)
        if not base_url:
            raise ValueError(
                f"La credencial de la herramienta '{herramienta.nombre}' "
                f"no tiene 'base_url' configurado en metadata (requerido para prevenir cross-wiring)."
            )
        url_final = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    # Validar SSRF ANTES de cualquier petición
    _validar_endpoint_seguro(url_final)

    # Timeout obligatorio: forzar float, rango 1-120, default 30
    # Rechazar strings aunque sean numéricos (solo int/float permitidos)
    timeout_raw = config.get("timeout", 30)
    if not isinstance(timeout_raw, (int, float)):
        raise ValueError("Timeout inválido: debe ser un número (int o float), no string.")
    try:
        timeout = float(timeout_raw)
    except (TypeError, ValueError):
        raise ValueError("Timeout inválido: debe ser un número.")

    if timeout <= 0 or timeout > 120:
        raise ValueError("Timeout inválido: debe estar entre 1 y 120 segundos.")

    # Método HTTP: allowlist estricta
    metodo = config.get("method", "POST").upper()
    if metodo not in ("GET", "POST", "PUT", "PATCH"):
        raise ValueError(f"Método HTTP no permitido: {metodo}. Permitidos: GET, POST, PUT, PATCH.")

    # Headers de autenticación
    headers = _construir_headers_autenticacion(config)

    # Headers adicionales de la configuración - BLOQUEAR override de headers protegidos
    extra_headers = config.get("headers", {})
    if isinstance(extra_headers, dict):
        for clave, valor in extra_headers.items():
            if isinstance(clave, str) and clave.lower() in _HEADERS_PROTEGIDOS:
                # Ignorar silenciosamente headers protegidos
                continue
            headers[clave] = valor

    # Log sanitizado (NUNCA el config crudo)
    # Sanitizar headers reemplazando el valor del secreto si aparece en algún header
    headers_para_log = dict(headers)
    secreto = config.get("secreto_desencriptado")
    if secreto:
        for clave, valor in headers_para_log.items():
            if isinstance(valor, str) and secreto in valor:
                headers_para_log[clave] = "***"

    logger.info(
        "Ejecutando herramienta '%s': %s %s",
        herramienta.nombre,
        metodo,
        _sanitizar_config({**config, "headers": headers_para_log}),
    )

    # Para credenciales tipo 'json', añadir secreto al payload si se especifica
    json_payload = dict(payload)
    if config.get("inject_secret_in_body") and config.get("secreto_desencriptado"):
        secret_key = config.get("secret_body_key", "api_key")
        if secret_key in json_payload:
            raise ValueError(
                f"La clave '{secret_key}' ya existe en el payload; "
                f"no se puede inyectar el secreto (prevención de colisión)."
            )
        json_payload[secret_key] = config["secreto_desencriptado"]

    try:
        response = requests.request(
            method=metodo,
            url=url_final,
            json=json_payload,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,  # OBLIGATORIO: no seguir redirecciones no validadas
        )
    except requests.RequestException as exc:
        # Relanzar excepción genérica SIN detalles sensibles (URL, headers, body)
        raise ToolExecutionError("Error de red al ejecutar la herramienta") from exc

    try:
        body = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        body = response.text

    # Post-procesamiento condicional para sitemap-reader: parsear el XML y devolver lista de URLs
    if herramienta.slug == "sitemap-reader" and response.status_code == 200:
        if isinstance(body, str):
            body = _parsear_sitemap(body)

    # Post-procesamiento condicional para seo-analyzer: analizar SEO on-page del HTML
    if herramienta.slug == "seo-analyzer" and response.status_code == 200:
        if isinstance(body, str):
            body = _analizar_seo_on_page(body, url_final)

    return {"status": response.status_code, "body": body}


# ============================================================
# Fachadas públicas para consumir desde vistas del panel (Paso C.6-A)
# Las funciones privadas (_validar_endpoint_seguro, _construir_headers_autenticacion)
# se mantienen intactas; estas fachadas solo delegan a las privadas.
# ============================================================

def validar_endpoint_seguro(url: str) -> None:
    """Fachada pública del validador SSRF. Consumida por views del panel."""
    return _validar_endpoint_seguro(url)


def construir_headers_autenticacion(config: dict) -> dict:
    """Fachada pública del builder de headers. Consumida por views del panel."""
    return _construir_headers_autenticacion(config)