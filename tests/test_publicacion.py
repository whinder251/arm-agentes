import pytest
import respx
import httpx
import xml.etree.ElementTree as ET
from django.utils import timezone
from apps.providers.wordpress import WordPressProvider, ErrorAutenticacion
from apps.engine.sitemap import generar_sitemap
from apps.core.models import Tarea, Habilidad

@pytest.mark.django_db
def test_wordpress_crear_borrador_exitoso():
    base_url = "https://example.com"
    api_key = "user:password"
    
    with respx.mock(base_url=f"{base_url}/wp-json/wp/v2") as respx_mock:
        respx_mock.post("/posts").mock(
            return_value=httpx.Response(201, json={"link": "https://example.com/mi-post/"})
        )
        
        with WordPressProvider(api_key, base_url) as provider:
            url = provider.crear_borrador("Título", "Contenido")
            assert url == "https://example.com/mi-post/"

@pytest.mark.django_db
def test_wordpress_crear_borrador_auth_error():
    base_url = "https://example.com"
    api_key = "user:password"
    
    with respx.mock(base_url=f"{base_url}/wp-json/wp/v2") as respx_mock:
        respx_mock.post("/posts").mock(
            return_value=httpx.Response(401)
        )
        
        with WordPressProvider(api_key, base_url) as provider:
            with pytest.raises(ErrorAutenticacion):
                provider.crear_borrador("Título", "Contenido")

@pytest.mark.django_db
def test_generar_sitemap():
    # Crear habilidades necesarias
    habilidad = Habilidad.objects.create(nombre="Test", slug="test")
    # Crear tareas de prueba en estado 'ok'
    t1 = Tarea.objects.create(estado="ok", habilidad=habilidad, actualizado_en=timezone.now(), payload={"slug": "post-uno"})
    t2 = Tarea.objects.create(estado="ok", habilidad=habilidad, actualizado_en=timezone.now(), payload={"slug": "post-dos"})
    
    tareas = Tarea.objects.filter(estado="ok")
    
    xml_output = generar_sitemap(tareas, base_url="https://ejemplo.com")
    
    # Validar que es XML válido
    root = ET.fromstring(xml_output)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    
    urls = root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    assert len(urls) == 2
    
    locs = [url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text for url in urls]
    assert "https://ejemplo.com/post-uno/" in locs
    assert "https://ejemplo.com/post-dos/" in locs
