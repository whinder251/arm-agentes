"""Pruebas del servicio de ejecución de investigaciones (Paso UX-2A).

Todas las peticiones HTTP se mockean; no se llama a APIs reales.
"""
import pytest
from datetime import timedelta
from unittest.mock import Mock, patch
from django.utils import timezone
from apps.core.models import (
    InvestigacionProgramada,
    Hallazgo,
    RegistroEjecucionMonitoreo,
)
from apps.engine import tasks
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
    def _crear_investigacion(
        self,
        urls="https://ejemplo.com/feed.rss",
        palabras_clave="",
        modo_busqueda="sitio",
        consulta_busqueda="",
    ):
        return InvestigacionProgramada.objects.create(
            nombre="Investigación de prueba",
            urls_objetivo=urls,
            frecuencia="semanal",
            palabras_clave=palabras_clave,
            modo_busqueda=modo_busqueda,
            consulta_busqueda=consulta_busqueda,
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

    def test_filtrado_por_palabras_clave_reporte_filtrados(self):
        """Cuando ninguna entrada coincide, filtrados > 0 y hallazgos_nuevos == 0."""
        investigacion = self._crear_investigacion(
            urls="https://ejemplo.com/feed.rss",
            palabras_clave="python, seguridad",
        )

        xml_sin_coincidencia = """<?xml version="1.0" encoding="UTF-8" ?>
        <rss version="2.0">
        <channel>
          <title>Feed de prueba</title>
          <item>
            <title>Recetas de cocina italiana</title>
            <link>https://ejemplo.com/cocina</link>
            <pubDate>Wed, 03 Jan 2024 00:00:00 GMT</pubDate>
            <description>Pasta y pizza casera</description>
          </item>
          <item>
            <title>Deportes internacionales</title>
            <link>https://ejemplo.com/deportes</link>
            <pubDate>Thu, 04 Jan 2024 00:00:00 GMT</pubDate>
            <description>Fútbol y baloncesto</description>
          </item>
        </channel>
        </rss>"""

        with patch("apps.engine.investigaciones.requests.get") as mock_get:
            mock_get.return_value = _mock_get(
                status_code=200, text=xml_sin_coincidencia
            )
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 0
        assert resultado["filtrados"] == 2
        assert resultado["fallos"] == []
        assert Hallazgo.objects.filter(investigacion=investigacion).count() == 0

    def test_extraccion_enlaces_de_html(self):
        """Sitio genérico (no WordPress): se ignora el <nav> con menú y solo
        se extrae el post principal dentro de <main>/<section class="card">
        con texto largo y fecha de <time>."""
        investigacion = self._crear_investigacion(
            urls="https://ejemplo.com/categoria",
        )

        html_categoria = """<!DOCTYPE html>
        <html>
        <body>
          <nav>
            <a href="https://ejemplo.com/inicio">Inicio</a>
            <a href="https://ejemplo.com/contacto">Contacto</a>
          </nav>
          <main>
            <section class="card">
              <a href="https://ejemplo.com/post-amazonas">
                Nuevo descubrimiento científico en el Amazonas
              </a>
              <time datetime="2026-11-18">18 de noviembre de 2026</time>
            </section>
          </main>
        </body>
        </html>"""

        def efecto_get(url, **kwargs):
            respuesta = Mock()
            respuesta.status_code = 200
            respuesta.text = html_categoria
            return respuesta

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract", return_value="contenido"
        ), patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 1
        # Solo el post del main, no los 2 enlaces del nav (texto corto).
        assert resultado["hallazgos_nuevos"] == 1
        assert resultado["filtrados"] == 0
        assert resultado["fallos"] == []

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion)
        assert hallazgos.count() == 1
        h = hallazgos.first()
        assert h.titulo == "Nuevo descubrimiento científico en el Amazonas"
        assert h.url_articulo == "https://ejemplo.com/post-amazonas"
        assert h.fecha_publicacion == "2026-11-18"
        assert h.tipo_fuente == "html"

    def test_modo_busqueda_registra_resultados_directo_como_hallazgos(self):
        """Modo 'busqueda': los resultados de DDG se registran directamente como
        hallazgos con sus metadatos (titulo, resumen, fecha), sin extraer enlaces
        internos de cada URL."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="busqueda",
            consulta_busqueda="competencia SEO",
        )

        resultados_ddgs = [
            {
                "href": "https://ejemplo.com/resultado-1",
                "title": "Resultado 1",
                "body": "Resumen 1",
                "date": "",
            },
            {
                "href": "https://ejemplo.com/resultado-2",
                "title": "Resultado 2",
                "body": "Resumen 2",
                "date": "",
            },
        ]

        class _DDGSMock:
            def text(self, consulta, max_results, **kwargs):
                return resultados_ddgs

        with patch("apps.engine.investigaciones.DDGS", return_value=_DDGSMock()), patch(
            "apps.engine.investigaciones._extraer_contenido", return_value="contenido extraído"
        ), patch("apps.engine.investigaciones.time.sleep"):
            resultado = ejecutar_investigacion(investigacion)

        # Se buscó en DuckDuckGo y se registraron los 2 resultados como hallazgos
        assert resultado["ejecutadas"] == 2
        assert resultado["hallazgos_nuevos"] == 2
        assert resultado["fallos"] == []

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by(
            "url_articulo"
        )
        assert hallazgos.count() == 2
        assert hallazgos[0].titulo == "Resultado 1"
        assert hallazgos[0].url_articulo == "https://ejemplo.com/resultado-1"
        assert hallazgos[0].resumen == "Resumen 1"
        assert hallazgos[0].fecha_publicacion == ""
        assert hallazgos[0].tipo_fuente == "html"
        assert hallazgos[1].titulo == "Resultado 2"
        assert hallazgos[1].url_articulo == "https://ejemplo.com/resultado-2"
        assert hallazgos[1].resumen == "Resumen 2"
        assert hallazgos[1].fecha_publicacion == ""
        assert hallazgos[1].tipo_fuente == "html"
        # No se crearon hallazgos para enlaces internos (articulo-a, articulo-b)
        assert not Hallazgo.objects.filter(
            investigacion=investigacion, url_articulo__contains="articulo-"
        ).exists()

    def test_modo_busqueda_con_fecha_guarda_fecha_publicacion(self):
        """Modo 'busqueda': si DDG devuelve fecha, se guarda en fecha_publicacion."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="busqueda",
            consulta_busqueda="competencia SEO",
        )

        resultados_ddgs = [
            {
                "href": "https://ejemplo.com/resultado-1",
                "title": "Resultado con fecha",
                "body": "Resumen con fecha",
                "date": "2026-11-18",
            },
        ]

        class _DDGSMock:
            def text(self, consulta, max_results, **kwargs):
                return resultados_ddgs

        with patch("apps.engine.investigaciones.DDGS", return_value=_DDGSMock()), patch(
            "apps.engine.investigaciones._extraer_contenido", return_value=""
        ), patch("apps.engine.investigaciones.time.sleep"):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["hallazgos_nuevos"] == 1
        h = Hallazgo.objects.filter(investigacion=investigacion).first()
        assert h.titulo == "Resultado con fecha"
        assert h.resumen == "Resumen con fecha"
        assert h.fecha_publicacion == "2026-11-18"
        assert h.tipo_fuente == "html"

    def test_modo_noticias_usa_google_news(self):
        """Modo 'noticias': construye URL de Google News y la procesa como RSS."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="noticias",
            consulta_busqueda="tecnología",
        )

        with patch("apps.engine.investigaciones.requests.get") as mock_get, patch(
            "apps.engine.investigaciones.trafilatura.extract", return_value="contenido"
        ), patch("apps.engine.investigaciones.time.sleep"):
            mock_get.return_value = _mock_get(status_code=200, text=XML_RSS)
            resultado = ejecutar_investigacion(investigacion)

        # 1 llamada a Google News + 2 llamadas para extraer contenido de los 2 artículos del RSS.
        assert mock_get.call_count == 3
        url_primera = mock_get.call_args_list[0][0][0]
        assert "news.google.com/rss/search" in url_primera
        assert "tecnología" in url_primera or "tecnolog%C3%ADa" in url_primera

        assert resultado["ejecutadas"] == 1
        assert resultado["hallazgos_nuevos"] == 2
        assert resultado["fallos"] == []

    def test_modo_busqueda_sin_consulta_no_procesa_nada(self):
        """Modo 'busqueda' sin consulta: no procesa URLs, sin fallos."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="busqueda",
            consulta_busqueda="",
        )

        resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 0
        assert resultado["hallazgos_nuevos"] == 0
        assert resultado["fallos"] == []

    def test_fallo_busqueda_duckduckgo_registra_error(self):
        """Si DDGS lanza excepción, el error se registra en fallos y no hay hallazgos."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="busqueda",
            consulta_busqueda="competencia SEO",
        )

        class _DDGSMockFallo:
            def text(self, consulta, max_results, **kwargs):
                raise Exception("Rate limit")

        with patch("apps.engine.investigaciones.DDGS", return_value=_DDGSMockFallo()):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["ejecutadas"] == 0
        assert resultado["hallazgos_nuevos"] == 0
        assert len(resultado["fallos"]) == 1
        assert "competencia SEO" in resultado["fallos"][0]["url"]
        assert "Rate limit" in resultado["fallos"][0]["error"]

    def test_busqueda_fallida_crea_registro_fallido_sin_tocar_ultima_ejecucion(self):
        """Si DDGS falla, se crea RegistroEjecucionMonitoreo con estado='fallido',
        ultima_ejecucion no cambia y el dict de retorno contiene el fallo."""
        investigacion = self._crear_investigacion(
            urls="",
            modo_busqueda="busqueda",
            consulta_busqueda="competencia SEO",
        )
        ultima_antes = investigacion.ultima_ejecucion

        class _DDGSMockFallo:
            def text(self, consulta, max_results, **kwargs):
                raise Exception("Rate limit")

        with patch("apps.engine.investigaciones.DDGS", return_value=_DDGSMockFallo()):
            resultado = ejecutar_investigacion(investigacion)

        investigacion.refresh_from_db()
        assert resultado["ejecutadas"] == 0
        assert resultado["hallazgos_nuevos"] == 0
        assert len(resultado["fallos"]) == 1
        assert "competencia SEO" in resultado["fallos"][0]["url"]
        assert "Rate limit" in resultado["fallos"][0]["error"]

        registros = RegistroEjecucionMonitoreo.objects.filter(investigacion=investigacion)
        assert registros.count() == 1
        reg = registros.first()
        assert reg.estado == "fallido"
        assert reg.fin is not None
        assert reg.hallazgos_nuevos == 0
        assert reg.filtrados == 0
        assert len(reg.fallos_detalle) == 1
        assert "Rate limit" in reg.fallos_detalle[0]["error"]

        assert investigacion.ultima_ejecucion == ultima_antes

    def test_no_desplaza_horario_despues_de_ejecucion_larga(self):
        """Una ejecución que tarda 10 minutos no desplaza la siguiente ejecución.

        ultima_ejecucion guarda la hora de INICIO (no el fin), por lo que el
        siguiente vencimiento se calcula desde la hora programada de esta
        ejecución y no desde cuándo terminó la anterior.
        """
        ahora = timezone.now()
        investigacion = InvestigacionProgramada.objects.create(
            nombre="Investigación de prueba",
            urls_objetivo="https://ejemplo.com/feed.rss",
            frecuencia="diaria",
            palabras_clave="",
            modo_busqueda="sitio",
            consulta_busqueda="",
            activa=True,
            ultima_ejecucion=ahora - timedelta(days=1),
        )

        # Simula una ejecución larga (10 min): las llamadas de red son mockeadas
        # para que la función real se ejecute rápido y persista ultima_ejecucion
        # con la hora de inicio, no con la de fin.
        with patch(
            "apps.engine.investigaciones._validar_endpoint_seguro"
        ), patch(
            "apps.engine.investigaciones.requests.get",
            return_value=_mock_get(200, XML_RSS),
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract", return_value="contenido"
        ), patch("apps.engine.investigaciones.time.sleep"):
            resultado = tasks.chequear_y_ejecutar_investigaciones.call_local()

        assert resultado == 1
        investigacion.refresh_from_db()

        # ultima_ejecucion debe ser la hora de inicio (~ahora), dentro de 120 s.
        delta_inicio = abs((investigacion.ultima_ejecucion - ahora).total_seconds())
        assert delta_inicio < 120, (
            f"ultima_ejecucion={investigacion.ultima_ejecucion} está demasiado "
            f"lejos del inicio {ahora} ({delta_inicio:.0f}s)"
        )

        # Y no debe estar desplazada 10 minutos hacia el futuro.
        desplazado = ahora + timedelta(minutes=10)
        assert investigacion.ultima_ejecucion < desplazado

    def test_sitemap_titulo_vacio_se_puebla_desde_pagina_descargada(self):
        """Sitemap sin título ni lastmod: al extraer contenido se puebla título, fecha y resumen
        desde la página ya descargada, sin peticiones extra."""
        investigacion = self._crear_investigacion(
            urls="https://ejemplo.com/sitemap.xml"
        )

        XML_SITEMAP_SIN_LASTMOD = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://ejemplo.com/pagina-1</loc>
  </url>
  <url>
    <loc>https://ejemplo.com/pagina-2</loc>
  </url>
</urlset>"""

        html_articulo = """<!DOCTYPE html>
        <html>
        <head>
          <title>Título real del artículo</title>
          <meta name="description" content="Resumen descriptivo del artículo.">
          <meta property="article:published_time" content="2026-11-18T10:00:00Z">
        </head>
        <body>
          <article>
            <h1>Título real del artículo</h1>
            <p>Contenido principal del artículo extraído con trafilatura.</p>
          </article>
        </body>
        </html>"""

        def efecto_get(url, **kwargs):
            respuesta = Mock()
            respuesta.status_code = 200
            if "sitemap" in url:
                respuesta.text = XML_SITEMAP_SIN_LASTMOD
            else:
                respuesta.text = html_articulo
            return respuesta

        metadata_mock = Mock()
        metadata_mock.title = "Título real del artículo"
        metadata_mock.date = "2026-11-18T10:00:00Z"
        metadata_mock.description = "Resumen descriptivo del artículo."

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract_metadata",
            return_value=metadata_mock,
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract",
            return_value="Contenido principal del artículo extraído con trafilatura.",
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
            assert h.titulo == "Título real del artículo"
            assert h.fecha_publicacion == "2026-11-18T10:00:00Z"
            assert h.resumen == "Resumen descriptivo del artículo."
            assert (
                h.contenido_extraido
                == "Contenido principal del artículo extraído con trafilatura."
            )

    def test_rss_titulo_bueno_no_se_pisa_con_pagina(self):
        """RSS con título bueno: al extraer contenido NO se pisa el título
        con el <title> de la página descargada."""
        investigacion = self._crear_investigacion()

        html_articulo = """<!DOCTYPE html>
        <html>
        <head>
          <title>Título de la página web</title>
        </head>
        <body>
          <p>Contenido de la página.</p>
        </body>
        </html>"""

        def efecto_get(url, **kwargs):
            respuesta = Mock()
            respuesta.status_code = 200
            if "feed.rss" in url:
                respuesta.text = XML_RSS
            else:
                respuesta.text = html_articulo
            return respuesta

        metadata_mock = Mock()
        metadata_mock.title = ""
        metadata_mock.date = ""
        metadata_mock.description = ""

        with patch(
            "apps.engine.investigaciones.requests.get", side_effect=efecto_get
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract_metadata",
            return_value=metadata_mock,
        ), patch(
            "apps.engine.investigaciones.trafilatura.extract",
            return_value="Contenido de la página.",
        ), patch(
            "apps.engine.investigaciones.time.sleep"
        ):
            resultado = ejecutar_investigacion(investigacion)

        assert resultado["hallazgos_nuevos"] == 2

        hallazgos = Hallazgo.objects.filter(investigacion=investigacion).order_by(
            "url_articulo"
        )
        assert hallazgos.count() == 2
        assert hallazgos[0].titulo == "Artículo 1"
        assert hallazgos[1].titulo == "Artículo 2"

    def test_reintenta_extraccion_si_hallazgo_existe_vacio(self):
        """Si un hallazgo ya existe con contenido_extraido vacío, se reintenta la extracción."""
        investigacion = self._crear_investigacion()

        Hallazgo.objects.create(
            investigacion=investigacion,
            url_articulo="https://ejemplo.com/articulo-1",
            url_fuente="https://ejemplo.com/feed.rss",
            tipo_fuente=Hallazgo.TipoFuente.RSS,
            titulo="Artículo existente",
            contenido_extraido="",
        )

        with patch(
            "apps.engine.investigaciones.requests.get",
            return_value=_mock_get(status_code=200, text=XML_RSS),
        ), patch(
            "apps.engine.investigaciones._extraer_contenido_enriquecido",
            return_value={
                "contenido": "Contenido re-extraído con éxito.",
                "titulo": "",
                "fecha": "",
                "resumen": "",
            },
        ), patch("apps.engine.investigaciones.time.sleep"):
            resultado = ejecutar_investigacion(investigacion)

        hallazgo = Hallazgo.objects.get(
            investigacion=investigacion,
            url_articulo="https://ejemplo.com/articulo-1",
        )
        assert hallazgo.contenido_extraido == "Contenido re-extraído con éxito."
