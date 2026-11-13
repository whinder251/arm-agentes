"""Adaptador para la API REST de WordPress (Application Passwords)."""

from __future__ import annotations

from typing import Any, Mapping
import httpx

from apps.providers.base import ErrorProveedor, TimeoutProveedor


class ErrorAutenticacion(ErrorProveedor):
    """Credenciales de WordPress inválidas (HTTP 401/403)."""


class ErrorCliente(ErrorProveedor):
    """Error del cliente en la API de WordPress (HTTP 4xx)."""


class ErrorServidor(ErrorProveedor):
    """Error del servidor en la API de WordPress (HTTP 5xx)."""


class WordPressProvider:
    """Proveedor para publicar y gestionar contenidos en WordPress."""

    nombre = "wordpress"

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0):
        if not api_key:
            raise ValueError("api_key es obligatoria")
        if ":" not in api_key:
            raise ValueError("api_key de WordPress debe tener formato 'usuario:contraseña'")
        self.username, self.password = api_key.split(":", 1)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            auth=httpx.BasicAuth(self.username, self.password),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WordPressProvider:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutProveedor(
                f"{self.nombre}: la petición superó {self.timeout} segundos"
            ) from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        code = response.status_code
        if code in (401, 403):
            raise ErrorAutenticacion(f"{self.nombre}: error de autenticación ({code})")
        if 400 <= code < 500:
            raise ErrorCliente(f"{self.nombre}: error del cliente ({code})")
        if 500 <= code < 600:
            raise ErrorServidor(f"{self.nombre}: error del servidor ({code})")
        response.raise_for_status()

    def crear_borrador(
        self,
        titulo: str,
        contenido: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """Crea un borrador en WordPress y devuelve su URL (link)."""
        payload: dict[str, Any] = {
            "title": titulo,
            "content": contenido,
            "status": "draft",
        }
        if metadata:
            for key in ("excerpt", "slug", "categories", "tags"):
                if key in metadata:
                    payload[key] = metadata[key]

        response = self._request(
            "POST",
            f"{self.base_url}/wp-json/wp/v2/posts",
            json=payload,
        )
        data = response.json()
        link = data.get("link")
        if not link:
            raise ErrorCliente(f"{self.nombre}: respuesta sin enlace (link)")
        return str(link)

    def publicar(self, borrador_id: int | str) -> str:
        """Publica un borrador existente y devuelve su URL (link)."""
        response = self._request(
            "POST",
            f"{self.base_url}/wp-json/wp/v2/posts/{borrador_id}",
            json={"status": "publish"},
        )
        data = response.json()
        link = data.get("link")
        if not link:
            raise ErrorCliente(f"{self.nombre}: respuesta sin enlace (link)")
        return str(link)
