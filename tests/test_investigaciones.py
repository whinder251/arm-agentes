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
    def _crear_investigacion(self, urls="https://ejemplo.com/feed.rss", palabras_clave=""):
        return InvestigacionProgramada.objects.create(
            nombre="Investigación de prueba",
            urls_objetivo=urls,
            frecuencia="semanal",
            palabras_clave=palabras_clave,
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
        ) as mock_get, patch(
            "apps.engine.investigaciones.trafilatura.extract",
            return_value="Texto extraído del artículo.",
        ), patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        # Se intentó descargar ambas URLs más la extracción de contenido de
        # los 2 artículos del feed válido (4 llamadas en total).
        assert mock_get.call_count == 4
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

    def test_ejecutar_investigacion_extrae_contenido_hallazgo(self):
        investigacion = self._crear_investigacion()

        def efecto_get(url, **kwargs):
            respuesta = Mock()
            respuesta.status_code = 200
            respuesta.text = XML_RSS
            return respuesta

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract",
            return_value="Texto principal del artículo extraído.",
        ), patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["hallazgos_nuevos"] == 2

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by(
            "url_articulo"
        )
        assert hallazgos.count() == 2
        for h in hallazgos:
            assert h.contenido_extraido == "Texto principal del artículo extraído."

    def test_ejecutar_investigacion_extraccion_http429_deja_campo_vacio(self):
        investigacion = self._crear_investigacion()

        llamadas = {"n": 0}

        def efecto_get(url, **kwargs):
            llamadas["n"] += 1
            respuesta = Mock()
            if llamadas["n"] == 1:
                # Primera llamada: descarga del feed (200 OK).
                respuesta.status_code = 200
                respuesta.text = XML_RSS
            else:
                # Llamadas de extracción de artículos: HTTP 429, sin reintento.
                respuesta.status_code = 429
                respuesta.text = ""
            return respuesta

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract"
        ) as mock_extract, patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["hallazgos_nuevos"] == 2
        # trafilatura nunca se invocó porque HTTP 429 se detiene antes.
        mock_extract.assert_not_called()

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion)
        assert hallazgos.count() == 2
        for h in hallazgos:
            assert h.contenido_extraido == ""

    def test_ejecutar_investigacion_extraccion_fallback_jina_ai(self):
        """Si trafilatura devuelve vacío, se intenta Jina AI y se guarda su texto."""
        investigacion = self._crear_investigacion()

        def efecto_get(url, **kwargs):
            respuesta = Mock()
            if url.startswith("https://r.jina.ai/"):
                # Nivel 2: Jina AI devuelve contenido simulado.
                respuesta.status_code = 200
                respuesta.text = "Contenido extraído por Jina AI del artículo."
            else:
                # Descarga del feed RSS (el HTML se usa para trafilatura en Nivel 1).
                respuesta.status_code = 200
                respuesta.text = XML_RSS
            return respuesta

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract", return_value=""
        ), patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["hallazgos_nuevos"] == 2

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by(
            "url_articulo"
        )
        assert hallazgos.count() == 2
        for h in hallazgos:
            assert h.contenido_extraido == "Contenido extraído por Jina AI del artículo."

    def test_filtrado_por_palabras_clave_en_fuente(self):
        investigacion = self._crear_investigacion(
            urls="https://ejemplo.com/feed.rss",
            palabras_clave="python, seguridad",
        )

        xml_filtrado = """<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
          <title>Feed de prueba</title>
          <item>
            <title>Aprender Python desde cero</title>
            <link>https://ejemplo.com/python</link>
            <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
            <description>Introducción a Python</description>
          </item>
          <item>
            <title>Seguridad en aplicaciones web</title>
            <link>https://ejemplo.com/seguridad</link>
            <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
            <description>Buenas prácticas de seguridad</description>
          </item>
          <item>
            <title>Recetas de cocina italiana</title>
            <link>https://ejemplo.com/cocina</link>
            <pubDate>Wed, 03 Jan 2024 00:00:00 GMT</pubDate>
            <description>Pasta y pizza casera</description>
          </item>
        </channel>
        </rss>"""

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(status_code=200, text=xml_filtrado)
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 2
        assert resultado["fallos"] == []

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by(
            "url_articulo"
        )
        assert hallazgos.count() == 2
        titulos = {h.titulo for h in hallazgos}
        assert "Aprender Python desde cero" in titulos
        assert "Seguridad en aplicaciones web" in titulos
        assert "Recetas de cocina italiana" not in titulos
