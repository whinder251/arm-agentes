"""Infraestructura de ejecución segura de herramientas.

Este módulo provee funciones para resolver e inyectar credenciales
desencriptadas en tiempo de ejecución, con validación SSRF, timeout
obligatorio y sanitizado de logs. Listo para ser consumido por el
orquestador (Fase 4) y por el botón "Probar conexión" del panel.
"""

import logging
import socket
from typing import Any
from urllib.parse import urlparse

import ipaddress
import requests

from apps.core.models import Credencial, Herramienta

logger = logging.getLogger(__name__)

# Claves que nunca deben aparecer en logs ni serializaciones
_CLAVES_SENSIBLES = {
    "api_key",
    "secreto",
    "password",
    "token",
    "secreto_desencriptado",
    "credentials_json",
    "app_password",
}

# Rangos IP bloqueados por política SSRF (IPv4 e IPv6)
_RANGOS_BLOQUEADOS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Privado RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # Privado RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # Privado RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local
    ipaddress.ip_network("::1/128"),          # Loopback IPv6
    ipaddress.ip_network("fc00::/7"),         # Unique local IPv6
]


def _sanitizar_config(config: dict) -> dict:
    """Devuelve una copia profunda del diccionario con claves sensibles enmascaradas.

    Sanitiza recursivamente diccionarios anidados (ej. headers) y valores
    que contengan patrones de secretos (Bearer, Basic, API keys).
    """
    _PATRONES_SENSIBLES = (
        "bearer ",
        "basic ",
        "api_key",
        "apikey",
    )

    def _contiene_secreto(valor: str) -> bool:
        if not isinstance(valor, str):
            return False
        v_lower = valor.lower()
        return any(p in v_lower for p in _PATRONES_SENSIBLES)

    def _sanitizar_valor(valor):
        if isinstance(valor, dict):
            return {k: _sanitizar_valor(v) for k, v in valor.items()}
        elif isinstance(valor, list):
            return [_sanitizar_valor(v) for v in valor]
        elif isinstance(valor, str) and _contiene_secreto(valor):
            return "***"
        return valor

    sanitizada = {}
    for clave, valor in config.items():
        if clave.lower() in _CLAVES_SENSIBLES:
            sanitizada[clave] = "***"
        else:
            sanitizada[clave] = _sanitizar_valor(valor)
    return sanitizada


def _validar_endpoint_seguro(url: str) -> None:
    """Valida que el endpoint no apunte a redes internas (SSRF).

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

        for rango in _RANGOS_BLOQUEADOS:
            if direccion in rango:
                raise ValueError(
                    f"Endpoint bloqueado por política SSRF: {ip_str} "
                    f"pertenece a rango restringido ({rango})."
                )


def _obtener_configuracion_ejecucion(herramienta: Herramienta) -> dict:
    """Fusiona la configuración de la herramienta con su credencial desencriptada.

    Prioridad de fusión (de menor a mayor precedencia):
    1. metadata de la credencial (base_url, username, header_scheme, etc.)
    2. configuración propia de la herramienta (endpoint, timeout, params)
    3. secreto_desencriptado (inyectado al final)

    Lanza ValueError si la credencial existe pero su secreto está vacío.
    """
    config = dict(herramienta.configuracion or {})

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

        # Fusionar: metadata < config < secreto
        config_ejecucion = {**metadata, **config}
        config_ejecucion["secreto_desencriptado"] = secreto
        return config_ejecucion

    return config


def _construir_headers_autenticacion(config: dict) -> dict:
    """Construye los headers de autenticación según el tipo de credencial."""
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
        import base64
        token = base64.b64encode(f"{username}:{secreto}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    # Para 'json' el secreto va en el body, no en headers

    return headers


def _ejecutar_herramienta_http(herramienta: Herramienta, payload: dict) -> dict:
    """Ejecuta una petición HTTP usando la herramienta y su credencial.

    Args:
        herramienta: Instancia de Herramienta con credencial opcional.
        payload: Diccionario con el cuerpo de la petición.

    Returns:
        Diccionario con 'status' (int) y 'body' (dict o str).

    Lanza:
        ValueError: Si falla la validación SSRF o falta credencial.
        requests.RequestException: Errores de red/HTTP propagados.
    """
    config = _obtener_configuracion_ejecucion(herramienta)

    # Determinar endpoint: prioridad endpoint > base_url
    # Si endpoint es ruta relativa y hay base_url, unirlos
    endpoint = config.get("endpoint")
    base_url = config.get("base_url")
    if endpoint and base_url and not endpoint.startswith(("http://", "https://")):
        from urllib.parse import urljoin
        endpoint = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))
    elif not endpoint:
        endpoint = base_url

    if not endpoint:
        raise ValueError(
            f"La herramienta '{herramienta.nombre}' no tiene 'endpoint' "
            f"ni 'base_url' configurados."
        )

    _validar_endpoint_seguro(endpoint)

    # Timeout obligatorio con default 30s
    timeout = config.get("timeout", 30)

    # Método HTTP (default POST)
    metodo = config.get("method", "POST").upper()

    # Headers de autenticación
    headers = _construir_headers_autenticacion(config)
    # Headers adicionales de la configuración
    extra_headers = config.get("headers", {})
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)

    # Log sanitizado (NUNCA el config crudo)
    logger.info(
        "Ejecutando herramienta '%s': %s %s",
        herramienta.nombre,
        metodo,
        _sanitizar_config({**config, "headers": headers}),
    )

    # Para credenciales tipo 'json', añadir secreto al payload si se especifica
    json_payload = dict(payload)
    if config.get("inject_secret_in_body") and config.get("secreto_desencriptado"):
        secret_key = config.get("secret_body_key", "api_key")
        json_payload[secret_key] = config["secreto_desencriptado"]

    response = requests.request(
        method=metodo,
        url=endpoint,
        json=json_payload,
        headers=headers,
        timeout=timeout,
    )

    try:
        body = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        body = response.text

    return {"status": response.status_code, "body": body}