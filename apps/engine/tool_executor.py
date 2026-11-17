"""Infraestructura de ejecución segura de herramientas.

Este módulo provee funciones para resolver e inyectar credenciales
desencriptadas en tiempo de ejecución, con validación SSRF, timeout
obligatorio y sanitizado de logs. Listo para ser consumido por el
orquestador (Fase 4) y por el botón "Probar conexión" del panel.
"""

import base64
import logging
import socket
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
    # endpoint SÍ puede venir de la herramienta (ruta específica)

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

    # Determinar endpoint: base_url OBLIGATORIO de credencial, endpoint de herramienta
    endpoint = config.get("endpoint")
    base_url = config.get("base_url")

    if not base_url:
        raise ValueError(
            f"La credencial de la herramienta '{herramienta.nombre}' "
            f"no tiene 'base_url' configurado en metadata (requerido para prevenir cross-wiring)."
        )

    if not endpoint:
        raise ValueError(
            f"La herramienta '{herramienta.nombre}' no tiene 'endpoint' configurado."
        )

    if base_url and not endpoint.startswith(("http://", "https://")):
        endpoint = urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))
    elif not base_url and not endpoint.startswith(("http://", "https://")):
        # Si no hay base_url, el endpoint debe ser URL absoluta
        raise ValueError(
            f"La herramienta '{herramienta.nombre}' requiere 'base_url' en la credencial "
            f"cuando 'endpoint' es una ruta relativa."
        )

    # Validar SSRF ANTES de cualquier petición
    _validar_endpoint_seguro(endpoint)

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
            url=endpoint,
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

    return {"status": response.status_code, "body": body}