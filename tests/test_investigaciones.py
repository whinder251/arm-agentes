"""Pruebas del servicio de ejecución de investigaciones (Paso UX-2A).

Todas las peticiones HTTP se mockean; no se llama a APIs reales.
"""
import pytest
from unittest.mock import Mock, patch
from django.utils import timezone
from apps.core.models import InvestigacionProgramada, Hallazgo
from apps.engine.investigaciones import ejecutar_investigacion, _detectar_tipo


XML_RSS = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>Feed de prueba</title>
  <item>
    <title>Artículo 1</title>
    <link>https://ejemplo.com/articulo-1</link>
    <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    <description>Resumen del artículo 1</description>
  </item>
  <item>
    <title>Artículo 2</title>
    <link>https://ejemplo.com/articulo-2</link>
    <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    <description>Resumen del artículo 2</description>
  </item>
</channel>
</rss>"""

XML_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://ejemplo.com/pagina-1</loc>
    <lastmod>2024-01-01</lastmod>
  </url>
  <url>
    <loc>https://ejemplo.com/pagina-2</loc>
    <lastmod>2024-01-02</lastmod>
  </url>
</urlset>"""

XML_INVALDO = "<no-es-un-feed>contenido basura</no-es-un-feed>"


def _mock_get(status_code=200, text=""):
    respuesta = Mock()
    respuesta.status_code = status_code
    respuesta.text = text
    return respuesta


@pytest.mark.django_db
class TestDetectarTipo:
    def test_detectar_tipo_sitemap(self):
        assert _detectar_tipo(XML_SITEMAP) == "sitemap"

    def test_detectar_tipo_rss(self):
        assert _detectar_tipo(XML_RSS) == "rss"

    def test_detectar_tipo_invalido_devuelve_desconocido(self):
        assert _detectar_tipo(XML_INVALDO) == "desconocido"
        assert _detectar_tipo("") == "desconocido"
        assert _detectar_tipo(None) == "desconocido"


@pytest.mark.django_db
class TestEjecutarInvestigacion:
    def _crear_investigacion(self, urls="https://ejemplo.com/feed.rss"):
        return InvestigacionProgramada.objects.create(
            nombre="Investigación de prueba",
            urls_objetivo=urls,
            frecuencia="semanal",
            activa=True,
        )

    def test_ejecutar_investigacion_guarda_hallazgos_rss(self):
        investigacion = self._crear_investigacion()
        assert investigacion.ultima_ejecucion is None

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(status_code=200, text=XML_RSS)
            resultado = ejecutar_investigacion(investigacion)

        investigacion.refresh_from_db()
        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 2
        assert resultado["fallos"] == []
        assert investigacion.ultima_ejecucion is not None

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by("url_articulo")
        assert hallazgos.count() == 2
        assert hallazgos[0].tipo_fuente == Hallazgo.TipoFuente.RSS
        assert hallazgos[0].titulo == "Artículo 1"
        assert hallazgos[0].url_articulo == "https://ejemplo.com/articulo-1"
        assert hallazgos[0].fecha_publicacion == "Mon, 01 Jan 2024 00:00:00 GMT"
        assert hallazgos[0].resumen == "Resumen del artículo 1"
        assert hallazgos[1].titulo == "Artículo 2"
        assert hallazgos[1].url_articulo == "https://ejemplo.com/articulo-2"

    def test_ejecutar_investigacion_guarda_hallazgos_sitemap(self):
        investigacion = self._crear_investigacion(
            urls="https://ejemplo.com/sitemap.xml"
        )

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(status_code=200, text=XML_SITEMAP)
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 2
        assert resultado["fallos"] == []

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion)
        assert hallazgos.count() == 2
        for h in hallazgos:
            assert h.tipo_fuente == Hallazgo.TipoFuente.SITEMAP
            assert h.titulo == ""
            assert h.resumen == ""

    def test_ejecutar_investigacion_deduplica(self):
        investigacion = self._crear_investigacion()

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(status_code=200, text=XML_RSS)
            resultado_primera = ejecutar_investigacion(investigacion)
            resultado_segunda = ejecutar_investigacion(investigacion)

        assert resultado_primera["hallazgos_nuevos"] == 2
        assert resultado_segunda["hallazgos_nuevos"] == 0
        assert Hallazgo.objects.filter(investigacion=investigacion).count() == 2

    def test_ejecutar_investigacion_no_rompe_con_url_fallando(self):
        investigacion = self._crear_investigacion(
            urls="https://host-falla.ejemplo/feed.rss\nhttps://ejemplo.com/feed.rss"
        )

        # socket.getaddrinfo resuelve a una IP pública para ambos hosts, así la
        # validación SSRF pasa y el fallo ocurre realmente en la petición HTTP.
        respuesta_publica = [
            (2, 1, 6, "", ("93.184.216.34", 0)),  # AF_INET, SOCK_STREAM, TCP
        ]

        def efecto_lateral(url, **kwargs):
            if "host-falla" in url:
                import requests as _requests

                raise _requests.RequestException("conexión rechazada")
            return _mock_get(status_code=200, text=XML_RSS)

        with patch("socket.getaddrinfo", return_value=respuesta_publica), patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_lateral
        ) as mock_get:
            resultado = ejecutar_investigacion(investigacion)

        # Se intentó descargar ambas URLs
        assert mock_get.call_count == 2
        # La fallida se registra, la buena se procesa
        assert len(resultado["fallos"]) == 1
        assert "host-falla" in resultado["fallos"][0]["url"]
        assert resultado["hallazgos_nuevos"] == 2
        assert Hallazgo.objects.filter(investigacion=investigacion).count() == 2

    def test_ejecutar_investigacion_status_no_200_registra_fallo(self):
        investigacion = self._crear_investigacion()

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(status_code=404, text="")
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 0
        assert len(resultado["fallos"]) == 1
        assert "HTTP 404" in resultado["fallos"][0]["error"]
        assert Hallazgo.objects.filter(investigacion=investigacion).count() == 0
