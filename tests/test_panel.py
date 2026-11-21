import os
import pytest
from unittest.mock import Mock, patch
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from apps.core.models import (
    Proveedor, ModeloLLM, Habilidad, Agente, Equipo, Tarea, Artefacto, Ejecucion,
    Workflow, PasoWorkflow, DestinoPublicacion, IntegracionConfig,
    InvestigacionProgramada, Hallazgo,
)
from apps.engine.tasks import continuar_workflow
from apps.panel.forms import InvestigacionForm

@pytest.mark.django_db
class TestPanel(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', password='testpass123')
        self.proveedor = Proveedor.objects.create(
            nombre='gemini', 
            api_key='fake', 
            base_url='http://test.invalid'
        )
        self.modelo = ModeloLLM.objects.create(
            proveedor=self.proveedor, 
            model_id='gemini-flash'
        )
        self.habilidad = Habilidad.objects.create(
            nombre='Reescritura', 
            slug='reescritura', 
            instrucciones='test', 
        )
        self.agente = Agente.objects.create(
            nombre='Editor', 
            modelo=self.modelo, 
            rol='Eres un editor experto.'
        )
        self.agente.habilidades.add(self.habilidad)
        IntegracionConfig.objects.create(
            nombre='ARM API',
            tipo='arm_api',
            activa=True,
        )

    def test_lista_requiere_login(self):
        url = reverse('lista_tareas')
        response = self.client.get(url)
        assert response.status_code == 302

    def test_lista_autenticado(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='cola',
            payload={'texto': 'hola'}
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_tareas')
        response = self.client.get(url)
        assert response.status_code == 200
        assert str(tarea.pk) in response.content.decode('utf-8')

    def test_detalle_tarea_autenticado(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'detalle text'}
        )
        Artefacto.objects.create(tarea=tarea, version=1, contenido='Artefacto 1', metadata={})
        Ejecucion.objects.create(tarea=tarea, modelo_usado='gemini-flash', tokens_in=10, tokens_out=20, ms=500)
        
        self.client.login(username='testuser', password='testpass123')
        url = reverse('detalle_tarea', args=[tarea.pk])
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert str(tarea.pk) in content
        assert 'Artefacto 1' in content
        assert 'gemini-flash' in content

    def test_aprobar_cambia_estado(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='revision',
            payload={'texto': 'revision text'}
        )
        artefacto = Artefacto.objects.create(
            tarea=tarea,
            version=1,
            contenido='Contenido revisado',
            metadata={'original': True}
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('aprobar_tarea')
        response = self.client.post(url, {'task_id': tarea.pk})
        
        tarea.refresh_from_db()
        assert tarea.estado == 'ok'
        
        artefacto.refresh_from_db()
        assert 'aprobado_por' in artefacto.metadata
        assert artefacto.metadata['aprobado_por'] == 'testuser'

    def test_aprobar_sin_login(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='revision',
            payload={'texto': 'revision text'}
        )
        url = reverse('aprobar_tarea')
        response = self.client.post(url, {'task_id': tarea.pk})
        assert response.status_code == 302
        tarea.refresh_from_db()
        assert tarea.estado == 'revision'

    def test_aprobar_htmx_devuelve_solo_fila(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='revision',
            payload={'texto': 'revision text'}
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('aprobar_tarea')
        response = self.client.post(url, {'task_id': tarea.pk}, HTTP_HX_REQUEST='true')

        content = response.content.decode('utf-8')
        assert response.status_code == 200
        assert f'<tr id="task-{tarea.pk}">' in content
        assert '<html' not in content
        assert 'Panel ARM' not in content
        assert 'Aprobar' not in content

        tarea.refresh_from_db()
        assert tarea.estado == 'ok'

    def test_sidebar_enlaza_configuracion(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_tareas'))
        content = response.content.decode('utf-8')
        # 4 items principales del navbar Centro de Mando
        assert 'Centro de Mando' in content
        assert 'Monitoreo' in content
        assert 'Biblioteca' in content
        assert f'href="{reverse("biblioteca")}"' in content
        assert 'Configuración' in content
        # Enlaces secundarios reubicados dentro del menú Configuración (details)
        assert f'href="{reverse("lista_proveedores")}"' in content
        assert f'href="{reverse("lista_modelos")}"' in content
        assert f'href="{reverse("configuracion")}"' in content
        assert 'Proveedores' in content
        assert 'Modelos' in content
        assert 'Modelos y proveedores' not in content

    def test_sidebar_activo_y_tokens_linear_nod(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_tareas'))
        content = response.content.decode('utf-8')
        # La clase .activo existe en el sidebar del HTML renderizado
        assert 'class="activo"' in content
        # El CSS de app.css contiene los tokens nuevos de Linear-Nod
        css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'app.css')
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()
        assert '--sidebar-bg' in css
        assert '--accent-solid' in css
        assert '--accent-on-dark' in css

    def test_dashboard_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('dashboard')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Panel de Control' in content
        assert 'Accesos Rápidos' in content
        assert 'Nueva Fuente de Monitoreo' in content
        assert 'Ver Ejecuciones' in content
        assert 'Gestionar Agentes' in content
        ctx = response.context
        assert isinstance(ctx['total_monitoreos'], int)
        assert isinstance(ctx['monitoreos_activos'], int)
        assert isinstance(ctx['ejecuciones_hoy'], int)
        assert isinstance(ctx['hallazgos_recientes'], int)
        assert isinstance(ctx['tokens_hoy'], int)
        assert isinstance(ctx['workflows_activos'], int)

    def test_integraciones_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('integraciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Integraciones del Sistema' in content
        assert 'Rotar Clave API' in content
        assert 'ARM API Key' not in content

    def test_lista_ejecuciones_render(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'texto de auditoría'}
        )
        Ejecucion.objects.create(
            tarea=tarea,
            modelo_usado='gemini-flash',
            tokens_in=10,
            tokens_out=20,
            ms=500,
            error='',
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_ejecuciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert str(tarea.pk) in content
        assert self.proveedor.nombre in content

    def test_crear_tarea_requiere_login(self):
        response = self.client.get(reverse('crear_tarea'))
        assert response.status_code == 302

    def test_crear_tarea_exitoso(self):
        seo = Habilidad.objects.create(
            nombre='SEO',
            slug='seo',
            instrucciones='test seo',
        )
        self.agente.habilidades.add(seo)
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'texto': 'Texto de prueba para reescribir.',
                'keyword': 'energía solar',
                'instrucciones': 'Tono cercano',
                'habilidad_id': self.habilidad.pk,
            })

        assert response.status_code == 302
        assert response.url == reverse('lista_tareas')
        tarea = Tarea.objects.get()
        assert tarea.estado == 'cola'
        assert tarea.agente == self.agente
        assert tarea.habilidad == self.habilidad
        assert tarea.payload['texto'] == 'Texto de prueba para reescribir.'
        assert tarea.payload['keyword'] == 'energía solar'
        assert tarea.payload['instrucciones'] == 'Tono cercano'
        encolar.assert_called_once_with(tarea.pk)

    def test_crear_tarea_con_habilidad_seleccionada(self):
        seo = Habilidad.objects.create(
            nombre='SEO',
            slug='seo',
            instrucciones='test seo',
        )
        self.agente.habilidades.add(seo)
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'texto': 'Texto para SEO.',
                'habilidad_id': seo.pk,
            })

        assert response.status_code == 302
        tarea = Tarea.objects.get()
        assert tarea.habilidad == seo
        assert tarea.habilidad != self.habilidad
        encolar.assert_called_once_with(tarea.pk)

    def test_crear_tarea_habilidad_inexistente(self):
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'texto': 'Texto de prueba.',
                'habilidad_id': 99999,
            })

        assert response.status_code == 302
        assert response.url == reverse('crear_tarea')
        assert Tarea.objects.count() == 0
        encolar.assert_not_called()

    def test_crear_tarea_sin_habilidad_id(self):
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'texto': 'Texto de prueba.',
            })

        assert response.status_code == 302
        tarea = Tarea.objects.get()
        assert tarea.habilidad == self.habilidad
        encolar.assert_called_once_with(tarea.pk)

    def test_crear_tarea_sin_agentes_activos(self):
        self.modelo.activo = False
        self.modelo.save()
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'texto': 'Texto de prueba para reescribir.',
                'keyword': 'energía solar',
            })

        assert response.status_code == 200
        assert 'No hay agentes activos disponibles' in response.content.decode('utf-8')
        assert Tarea.objects.count() == 0
        encolar.assert_not_called()

    def test_crear_tarea_sin_keyword(self):
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'agente_id': self.agente.pk,
                'texto': 'Texto de prueba para reescribir.',
            })

        assert response.status_code == 302
        tarea = Tarea.objects.get()
        assert tarea.agente == self.agente
        assert tarea.payload == {'texto': 'Texto de prueba para reescribir.'}
        assert 'keyword' not in tarea.payload
        encolar.assert_called_once_with(tarea.pk)

    def test_eliminar_tarea_exitoso(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='cola',
            payload={'texto': 'tarea a eliminar'}
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('eliminar_tarea', args=[tarea.pk]))

        assert response.status_code == 302
        assert response.url == reverse('lista_tareas')
        assert not Tarea.objects.filter(pk=tarea.pk).exists()

    def test_eliminar_tarea_get_no_permitido(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='cola',
            payload={'texto': 'tarea protegida'}
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('eliminar_tarea', args=[tarea.pk]))

        assert response.status_code == 405
        assert Tarea.objects.filter(pk=tarea.pk).exists()

    def test_publicar_tarea_exitoso(self):
        """Publicar con DestinoPublicacion usa sus credenciales, no las del proveedor LLM."""
        proveedor_wp = Proveedor.objects.create(
            nombre='wordpress',
            api_key='usuario:contraseña',
            base_url='http://wp.test.invalid',
        )
        modelo_wp = ModeloLLM.objects.create(
            proveedor=proveedor_wp, model_id='wp-modelo'
        )
        agente_wp = Agente.objects.create(
            nombre='Agente WP', modelo=modelo_wp, rol='Publicador'
        )
        agente_wp.habilidades.add(self.habilidad)
        tarea = Tarea.objects.create(
            agente=agente_wp,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'Contenido de prueba'},
        )
        Artefacto.objects.create(
            tarea=tarea, version=1,
            contenido='Contenido del artículo para publicar en WordPress.',
            metadata={},
        )
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Principal',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='usuario-blog',
            credenciales='contraseña-blog-secreta',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        with patch('apps.panel.views.WordPressProvider') as mock_wp:
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'http://wp.test.invalid/123'
            response = self.client.post(url, {'destino_id': str(destino.pk)})

        assert response.status_code == 302
        assert response.url == reverse('detalle_tarea', args=[tarea.pk])
        mock_wp.assert_called_once_with(
            api_key='usuario-blog:contraseña-blog-secreta',
            base_url='https://blog.ejemplo.com',
        )
        tarea.refresh_from_db()
        assert tarea.payload.get('wordpress_link') == 'http://wp.test.invalid/123'
        assert tarea.payload.get('enviado_a_wordpress') is True

    def test_publicar_tarea_con_destino_publicacion(self):
        """Publicar usa credenciales del DestinoPublicacion, no del Proveedor LLM."""
        proveedor_wp = Proveedor.objects.create(
            nombre='wordpress-llm',
            api_key='usuario-llm:contraseña-llm',
            base_url='http://wp-llm.test.invalid',
        )
        modelo_wp = ModeloLLM.objects.create(
            proveedor=proveedor_wp, model_id='wp-modelo-llm'
        )
        agente_wp = Agente.objects.create(
            nombre='Agente WP LLM', modelo=modelo_wp, rol='Publicador'
        )
        agente_wp.habilidades.add(self.habilidad)
        tarea = Tarea.objects.create(
            agente=agente_wp,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'Contenido de prueba'},
        )
        Artefacto.objects.create(
            tarea=tarea, version=1,
            contenido='Contenido del artículo para publicar en WordPress.',
            metadata={},
        )
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Principal',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='usuario-blog',
            credenciales='contraseña-blog-secreta',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        with patch('apps.panel.views.WordPressProvider') as mock_wp:
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'https://blog.ejemplo.com/123'
            response = self.client.post(url, {'destino_id': str(destino.pk)})

        assert response.status_code == 302
        assert response.url == reverse('detalle_tarea', args=[tarea.pk])
        # Se instanciaron con las credenciales del DestinoPublicacion, no del proveedor LLM
        mock_wp.assert_called_once_with(
            api_key='usuario-blog:contraseña-blog-secreta',
            base_url='https://blog.ejemplo.com',
        )
        tarea.refresh_from_db()
        assert tarea.payload.get('wordpress_link') == 'https://blog.ejemplo.com/123'
        assert tarea.payload.get('enviado_a_wordpress') is True
        # El api_key del proveedor LLM no debe persistirse en el payload
        assert 'usuario-llm:contraseña-llm' not in str(tarea.payload)
        assert 'contraseña-llm' not in str(tarea.payload)

    def test_publicar_tarea_sin_destino_falla(self):
        """Sin destino_id, la vista rechaza con mensaje de error y redirige."""
        proveedor_wp = Proveedor.objects.create(
            nombre='wordpress',
            api_key='usuario:contraseña',
            base_url='http://wp.test.invalid',
        )
        modelo_wp = ModeloLLM.objects.create(
            proveedor=proveedor_wp, model_id='wp-modelo'
        )
        agente_wp = Agente.objects.create(
            nombre='Agente WP', modelo=modelo_wp, rol='Publicador'
        )
        agente_wp.habilidades.add(self.habilidad)
        tarea = Tarea.objects.create(
            agente=agente_wp,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'Contenido de prueba'},
        )
        Artefacto.objects.create(
            tarea=tarea, version=1,
            contenido='Contenido del artículo para publicar en WordPress.',
            metadata={},
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        with patch('apps.panel.views.WordPressProvider') as mock_wp:
            response = self.client.post(url, follow=True)

        assert mock_wp.call_count == 0
        assert response.status_code == 200
        content = response.content.decode('utf-8', errors='ignore')
        assert "Debe configurar y seleccionar un Destino de Publicación válido" in content

    def _crear_tarea_para_publicar(self, contenido, metadata):
        """Helper: tarea en estado 'ok' con un artefacto y un destino activo."""
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Test',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='usuario',
            credenciales='pass',
            activa=True,
        )
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='ok',
            payload={'texto': 'Contenido de prueba'},
        )
        Artefacto.objects.create(
            tarea=tarea, version=1,
            contenido=contenido,
            metadata=metadata,
        )
        return destino, tarea

    def test_publicar_tarea_tipo_pagina(self):
        """tipo_publicacion='page' construye la petición contra el endpoint /pages de WordPress."""
        destino, tarea = self._crear_tarea_para_publicar(
            'Contenido', {'titulo': 'Mi Página'},
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        fake_response = Mock()
        fake_response.json.return_value = {"link": "https://blog.ejemplo.com/page/1"}
        with patch(
            'apps.providers.wordpress.WordPressProvider._request',
            return_value=fake_response,
        ) as mock_req:
            response = self.client.post(url, {
                'destino_id': str(destino.pk),
                'tipo_publicacion': 'page',
            })

        assert response.status_code == 302
        llamada_url = mock_req.call_args.args[1]
        assert '/wp-json/wp/v2/pages' in llamada_url

    def test_publicar_tarea_mapea_metadatos_estructurados(self):
        """slug, meta_description y focus_keyword se envían al payload de WordPress."""
        destino, tarea = self._crear_tarea_para_publicar(
            'Contenido',
            {
                'titulo': 'Título con meta',
                'slug': 'mi-slug',
                'meta_description': 'Descripción meta',
                'focus_keyword': 'palabra clave',
            },
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        with patch('apps.panel.views.WordPressProvider') as mock_wp:
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'https://blog.ejemplo.com/post/1'
            response = self.client.post(url, {
                'destino_id': str(destino.pk),
                'tipo_publicacion': 'post',
            })

        assert response.status_code == 302
        kwargs = instance.crear_borrador.call_args.kwargs
        assert kwargs.get('slug') == 'mi-slug'
        assert kwargs.get('meta_description') == 'Descripción meta'
        assert kwargs.get('focus_keyword') == 'palabra clave'

    def test_publicar_tarea_convierte_markdown_a_html(self):
        """El contenido Markdown se convierte a HTML antes de enviarse a WordPress."""
        destino, tarea = self._crear_tarea_para_publicar(
            '# Título MD', {'titulo': 'Título'},
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('publicar_tarea', args=[tarea.pk])

        with patch('apps.panel.views.WordPressProvider') as mock_wp:
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'https://blog.ejemplo.com/post/1'
            response = self.client.post(url, {
                'destino_id': str(destino.pk),
                'tipo_publicacion': 'post',
            })

        assert response.status_code == 302
        kwargs = instance.crear_borrador.call_args.kwargs
        assert kwargs.get('contenido') == '<h1>Título MD</h1>'
        assert '# Título MD' not in kwargs.get('contenido', '')

    def test_crear_tarea_formulario_chat(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('crear_tarea'))
        content = response.content.decode('utf-8')

        assert response.status_code == 200
        assert 'Procesar con IA' in content
        assert 'rows="12"' in content
        assert 'placeholder="Escribe o pega aquí el contenido que quieres procesar..."' in content
        assert 'name="keyword"' in content
        assert 'name="agente_id"' in content
        assert 'name="instrucciones"' in content
        assert '<option value="">Asignación automática</option>' in content

    def test_crear_tarea_sin_cuota_disponible(self):
        proveedor = Proveedor.objects.create(
            nombre='proveedor cuota',
            api_key='fake',
            base_url='http://test.invalid',
            limite_tokens_diario=100,
            tokens_consumidos_hoy=100,
        )
        modelo = ModeloLLM.objects.create(
            proveedor=proveedor, model_id='modelo-cuota'
        )
        agente = Agente.objects.create(
            nombre='Agente cuota', modelo=modelo, rol='Rol'
        )
        agente.habilidades.add(self.habilidad)
        self.client.login(username='testuser', password='testpass123')

        with patch('apps.panel.views.ejecutar_tarea') as encolar:
            response = self.client.post(reverse('crear_tarea'), {
                'agente_id': agente.pk,
                'texto': 'Texto de prueba para reescribir.',
            })

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'El proveedor ha alcanzado su límite diario de tokens.' in content
        assert Tarea.objects.count() == 0
        encolar.assert_not_called()

    def test_lista_muestra_formulario_eliminar(self):
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='cola',
            payload={'texto': 'tarea con boton eliminar'}
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_tareas'))
        content = response.content.decode('utf-8')
        accion = reverse('eliminar_tarea', args=[tarea.pk])

        assert response.status_code == 200
        assert f'<form method="post" action="{accion}"' in content
        assert 'btn-eliminar-tarea' in content
        assert '>Eliminar</button>' in content

    def test_lista_workflows_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_workflows')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Workflows' in content
        assert 'Nombre' in content
        assert 'Descripci' in content
        assert 'Estado' in content
        assert 'N&ordm; de Pasos' in content or 'Nº de Pasos' in content
        assert 'Fecha' in content
        assert 'Nuevo Workflow' in content

    def test_crear_workflow_exitoso(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_workflow')
        data = {
            'nombre': 'Campaña SEO',
            'descripcion': 'Flujo de reescritura y optimizaci&oacute;n.',
            'pasos-TOTAL_FORMS': '1',
            'pasos-INITIAL_FORMS': '0',
            'pasos-MIN_NUM_FORMS': '0',
            'pasos-MAX_NUM_FORMS': '1000',
            'pasos-0-orden': '1',
            'pasos-0-habilidad': self.habilidad.pk,
            'pasos-0-agente': self.agente.pk,
            'pasos-0-modo_ejecucion': 'auto',
        }
        response = self.client.post(url, data)
        assert response.status_code == 302
        assert response.url == reverse('lista_workflows')
        assert Workflow.objects.filter(nombre='Campaña SEO').exists()
        workflow = Workflow.objects.get(nombre='Campaña SEO')
        assert workflow.descripcion == 'Flujo de reescritura y optimizaci&oacute;n.'
        paso = PasoWorkflow.objects.filter(workflow=workflow).first()
        assert paso is not None
        assert paso.orden == 1
        assert paso.habilidad == self.habilidad
        assert paso.agente == self.agente
        assert paso.modo_ejecucion == 'auto'

    def test_crud_equipo_exitoso(self):
        agente2 = Agente.objects.create(
            nombre="Agente 2", rol="Rol 2", modelo=self.modelo
        )
        self.client.login(username='testuser', password='testpass123')

        url = reverse('crear_equipo')
        data = {
            'nombre': 'Equipo SEO',
            'descripcion': 'Equipo de prueba',
            'agentes': [self.agente.pk, agente2.pk],
        }
        response = self.client.post(url, data)
        assert response.status_code == 302
        assert response.url == reverse('lista_equipos')

        equipo = Equipo.objects.get(nombre='Equipo SEO')
        assert equipo.descripcion == 'Equipo de prueba'
        assert equipo.agentes.count() == 2
        assert self.agente in equipo.agentes.all()
        assert agente2 in equipo.agentes.all()

        # Lista muestra el equipo creado
        response = self.client.get(reverse('lista_equipos'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Equipo SEO' in content
        assert '2' in content

    def test_sidebar_contiene_workflows_y_equipos(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_tareas'))
        content = response.content.decode('utf-8')
        # Workflows y Equipos se reubicaron al menú secundario (details)
        assert f'href="{reverse("lista_workflows")}"' in content
        assert f'href="{reverse("lista_equipos")}"' in content
        assert 'Workflows' in content
        assert 'Equipos' in content
        # Los 4 items principales del navbar Centro de Mando siguen presentes
        assert 'Centro de Mando' in content
        assert 'Monitoreo' in content
        assert 'Biblioteca' in content
        assert 'Configuración' in content

    def test_configuracion_render(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configuracion'))
        assert response.status_code == 200

    def test_lista_agentes_render(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_agentes'))
        assert response.status_code == 200

    def test_editar_agente_guarda_habilidades(self):
        self.client.login(username='testuser', password='testpass123')
        # Agente existente con 1 habilidad (self.habilidad)
        nueva_h1 = Habilidad.objects.create(
            nombre='Investigación',
            slug='investigacion',
            instrucciones='test',
        )
        nueva_h2 = Habilidad.objects.create(
            nombre='Redacción',
            slug='redaccion',
            instrucciones='test',
        )
        url = reverse('editar_agente', args=[self.agente.pk])
        response = self.client.post(url, {
            'nombre': 'Editor',
            'rol': 'Eres un editor experto.',
            'temperatura': 0.7,
            'modelo': self.modelo.pk,
            'habilidades': [nueva_h1.pk, nueva_h2.pk],
        })
        self.agente.refresh_from_db()
        ids = set(self.agente.habilidades.values_list("id", flat=True))
        assert ids == {nueva_h1.pk, nueva_h2.pk}
        assert response.status_code == 302

    def test_lista_habilidades_render(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_habilidades'))
        assert response.status_code == 200

    def test_configuracion_form_oculto(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('configuracion'))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'form-oculto' in content

    def test_lista_proveedores_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_proveedores')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Proveedores' in content
        assert 'Gestión de proveedores y modelos de IA' in content
        assert self.proveedor.nombre in content
        assert self.modelo.model_id in content

    def test_lista_modelos_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_modelos')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Modelos' in content
        assert 'Gestión de modelos de IA por proveedor' in content
        assert self.modelo.model_id in content
        assert self.proveedor.nombre in content

    def test_editar_proveedor_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Editar proveedor' in content
        assert self.proveedor.nombre in content
        assert '****' in content
        assert 'Cambiar API key' not in content  # checkbox eliminado

    def test_editar_proveedor_dejar_vacio_conserva_clave(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        clave_original = self.proveedor.api_key
        response = self.client.post(url, {
            'nombre': 'gemini-editado',
            'base_url': 'http://editado.invalid',
            'api_key': '',  # vacío = conservar
            'rpm': '100',
            'limite_diario': '1000',
        })
        assert response.status_code == 302
        assert response.url == reverse('lista_proveedores')
        self.proveedor.refresh_from_db()
        assert self.proveedor.api_key == clave_original

    def test_editar_proveedor_escribir_nueva_clave_actualiza(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        nueva_clave = 'sk-nueva-clave-secreta-1234'
        response = self.client.post(url, {
            'nombre': 'gemini-editado',
            'base_url': 'http://editado.invalid',
            'api_key': nueva_clave,  # escribir nueva clave
            'rpm': '100',
            'limite_diario': '1000',
        })
        assert response.status_code == 302
        assert response.url == reverse('lista_proveedores')
        self.proveedor.refresh_from_db()
        assert self.proveedor.api_key == nueva_clave

    def test_editar_proveedor_placeholder_enmascarado_conserva(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        clave_original = self.proveedor.api_key
        response = self.client.post(url, {
            'nombre': 'gemini-editado',
            'base_url': 'http://editado.invalid',
            'api_key': '****fake',  # placeholder enmascarado
            'rpm': '100',
            'limite_diario': '1000',
        })
        assert response.status_code == 302
        assert response.url == reverse('lista_proveedores')
        self.proveedor.refresh_from_db()
        assert self.proveedor.api_key == clave_original

    def test_integraciones_render_muestra_destinos(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('integraciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Integraciones del Sistema' in content
        assert 'Rotar Clave API' in content
        assert 'Conexiones de Publicación' in content
        assert 'Añadir Conexión' in content

    def test_crear_destino_publicacion(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('integraciones')
        response = self.client.post(url, {
            'crear_destino': '1',
            'nombre': 'Blog Principal',
            'tipo': 'wordpress',
            'url': 'https://blog.ejemplo.com',
            'usuario': 'admin',
            'credenciales': 'contraseña-app-secreta',
            'activa': 'on',
        })
        assert response.status_code == 302
        assert response.url == reverse('integraciones')
        from apps.core.models import DestinoPublicacion
        destino = DestinoPublicacion.objects.get(nombre='Blog Principal')
        assert destino.url == 'https://blog.ejemplo.com'
        assert destino.tipo == 'wordpress'
        assert destino.credenciales == 'contraseña-app-secreta'
        assert destino.activa is True

    def test_editar_destino_preserva_credenciales(self):
        self.client.login(username='testuser', password='testpass123')
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Editor',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='admin',
            credenciales='credencial-super-secreta-12345',
            activa=True,
        )
        credencial_original = destino.credenciales
        url = reverse('editar_destino', kwargs={'pk': destino.pk})
        response = self.client.post(url, {
            'nombre': 'Blog Editor Editado',
            'tipo': 'wordpress',
            'url': 'https://blog.ejemplo.com',
            'usuario': 'admin',
            'activa': 'on',
        })
        assert response.status_code == 302
        assert response.url == reverse('integraciones')
        destino.refresh_from_db()
        assert destino.nombre == 'Blog Editor Editado'
        assert destino.credenciales == credencial_original

    def test_editar_destino_credenciales_enmascaradas_y_toggle(self):
        self.client.login(username='testuser', password='testpass123')
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Toggle',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='admin',
            credenciales='credencial-toggle-9876',
            activa=True,
        )
        url = reverse('editar_destino', kwargs={'pk': destino.pk})
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # El form aplica el enmascaramiento de credenciales (**** + últimos 4 chars).
        # Nota: PasswordInput de Django no renderiza el value en el HTML por seguridad,
        # por lo que se valida a través del contexto del form.
        assert response.context['form_destino'].initial['credenciales'] == '****9876'
        # Checkbox y textarea del toggle presentes
        assert 'id_cambiar_credenciales' in content
        assert 'id_nueva_credenciales' in content
        assert 'nueva_credenciales_group' in content
        # El textarea inicia oculto (clase form-oculto)
        assert 'form-oculto' in content

    def test_eliminar_destino(self):
        self.client.login(username='testuser', password='testpass123')
        destino = DestinoPublicacion.objects.create(
            nombre='Blog Borrar',
            tipo='wordpress',
            url='https://blog.ejemplo.com',
            usuario='admin',
            credenciales='credencial-borrar-12345',
            activa=True,
        )
        url = reverse('eliminar_destino', kwargs={'pk': destino.pk})
        response = self.client.post(url)
        assert response.status_code == 302
        assert response.url == reverse('integraciones')
        assert not DestinoPublicacion.objects.filter(pk=destino.pk).exists()

    def test_aprobar_tarea_reanuda_workflow(self):
        """Al aprobar una tarea en revisión con paso_workflow, se crea la tarea del siguiente paso en cola."""
        workflow = Workflow.objects.create(
            nombre='WF prueba', descripcion='wf', estado='en_ejecucion'
        )
        paso1 = PasoWorkflow.objects.create(
            workflow=workflow, orden=1,
            habilidad=self.habilidad, agente=self.agente, modo_ejecucion='auto'
        )
        paso2 = PasoWorkflow.objects.create(
            workflow=workflow, orden=2,
            habilidad=self.habilidad, agente=self.agente, modo_ejecucion='auto'
        )
        tarea = Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='revision',
            payload={'texto': 'revision wf'},
            paso_workflow=paso1,
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('aprobar_tarea')
        with patch('apps.engine.tasks.ejecutar_tarea') as mock_ejecutar:
            response = self.client.post(url, {'task_id': tarea.pk})
            # Simular el worker de Huey ejecutando la continuación encolada por la vista.
            continuar_workflow.func(workflow.pk, paso1.orden + 1)
        tarea.refresh_from_db()
        assert tarea.estado == 'ok'
        # Se creó la tarea del paso 2 en cola
        tarea_paso2 = Tarea.objects.filter(
            paso_workflow=paso2, estado='cola'
        ).first()
        assert tarea_paso2 is not None
        assert tarea_paso2.habilidad == self.habilidad
        # ejecutar_tarea fue invocado para la nueva tarea del paso 2
        mock_ejecutar.assert_called_once()

    def test_integraciones_rotar_clave_sin_500(self):
        """Rotar la clave ARM en integraciones no lanza UnboundLocalError ni 500."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('integraciones')
        response = self.client.post(url, {'rotar_arm_api': '1'})
        assert response.status_code in (200, 302)

    def test_lista_tareas_paginacion(self):
        """La lista de tareas pagina correctamente (20 por página)."""
        self.client.login(username='testuser', password='testpass123')
        # Crear 25 tareas
        for i in range(25):
            Tarea.objects.create(
                agente=self.agente,
                habilidad=self.habilidad,
                estado='cola',
                payload={'texto': f'tarea {i}'}
            )
        url = reverse('lista_tareas')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Primera página: 20 tareas
        assert 'Página 1 de 2' in content
        # Verificar que hay checkboxes
        assert 'name="task_ids"' in content
        assert 'id="select-all-tasks"' in content
        # Verificar nueva estructura de tarjetas de actividad del Centro de Mando
        assert 'class="card"' in content
        assert 'Aprobar y Procesar' in content
        assert 'Archivar / Descartar' in content
        # Segunda página
        response = self.client.get(url + '?page=2')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Página 2 de 2' in content

    def test_lista_tareas_filtro_estado_con_paginacion(self):
        """El filtro de estado funciona con paginación."""
        self.client.login(username='testuser', password='testpass123')
        t_cola = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='cola', payload={'texto': 'c1'})
        t_ok1 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': 'o1'})
        t_ok2 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': 'o2'})
        url = reverse('lista_tareas') + '?estado=ok'
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Página 1 de 1' in content
        # Verificar que la tabla contiene las tareas en estado 'ok' (buscar por ID en enlace de detalle)
        assert f'href="{reverse("detalle_tarea", args=[t_ok1.pk])}"' in content
        assert f'href="{reverse("detalle_tarea", args=[t_ok2.pk])}"' in content
        # Verificar que la tarea en cola NO está en la tabla
        assert f'href="{reverse("detalle_tarea", args=[t_cola.pk])}"' not in content

    def test_lista_tareas_feed_conversacional(self):
        """El Centro de Mando muestra contadores reales y texto narrativo del agente."""
        self.client.login(username='testuser', password='testpass123')

        investigacion_archivar = InvestigacionProgramada.objects.create(
            nombre='Inv archivo',
            urls_objetivo='https://ejemplo.com',
            modo_resultado='archivar',
            activa=True,
        )
        Hallazgo.objects.create(
            investigacion=investigacion_archivar,
            url_fuente='https://ejemplo.com/a',
            tipo_fuente='html',
            titulo='Artículo A',
        )
        Hallazgo.objects.create(
            investigacion=investigacion_archivar,
            url_fuente='https://ejemplo.com/b',
            tipo_fuente='html',
            titulo='Artículo B',
        )
        Tarea.objects.create(
            agente=self.agente,
            habilidad=self.habilidad,
            estado='revision',
            payload={'texto': 'pendiente'},
        )

        url = reverse('lista_tareas')
        response = self.client.get(url)
        assert response.status_code == 200

        assert response.context['total_hallazgos_hoy'] == 2
        assert response.context['pendientes_aprobacion'] == 1
        assert response.context['archivados_hoy'] == 2

        content = response.content.decode('utf-8')
        assert 'He sincronizado tus fuentes' in content
        assert 'descubrimientos' in content
        assert 'requieren tu aprobación' in content
        assert 'fueron archivados' in content

    def test_acciones_lote_tareas_eliminar(self):
        """Acción por lote: eliminar varias tareas."""
        self.client.login(username='testuser', password='testpass123')
        t1 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='cola', payload={'texto': 't1'})
        t2 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='cola', payload={'texto': 't2'})
        t3 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='cola', payload={'texto': 't3'})
        url = reverse('acciones_lote_tareas')
        response = self.client.post(url, {
            'action': 'eliminar',
            'task_ids': [t1.pk, t3.pk]
        })
        assert response.status_code == 302
        assert not Tarea.objects.filter(pk=t1.pk).exists()
        assert Tarea.objects.filter(pk=t2.pk).exists()  # t2 no seleccionada
        assert not Tarea.objects.filter(pk=t3.pk).exists()

    def test_acciones_lote_tareas_aprobar(self):
        """Acción por lote: aprobar tareas en revisión."""
        self.client.login(username='testuser', password='testpass123')
        t1 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='revision', payload={'texto': 't1'})
        t2 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='cola', payload={'texto': 't2'})  # no en revision
        t3 = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='revision', payload={'texto': 't3'})
        url = reverse('acciones_lote_tareas')
        response = self.client.post(url, {
            'action': 'aprobar',
            'task_ids': [t1.pk, t2.pk, t3.pk]
        })
        assert response.status_code == 302
        t1.refresh_from_db()
        t2.refresh_from_db()
        t3.refresh_from_db()
        assert t1.estado == 'ok'
        assert t2.estado == 'cola'  # no cambia porque no estaba en revision
        assert t3.estado == 'ok'

    def test_acciones_lote_tareas_sin_seleccion(self):
        """Acción por lote sin tareas seleccionadas muestra warning."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('acciones_lote_tareas')
        response = self.client.post(url, {'action': 'eliminar'})
        assert response.status_code == 302
        # Verificar mensaje de warning
        response = self.client.get(reverse('lista_tareas'))
        content = response.content.decode('utf-8')
        assert 'No se seleccionó ninguna tarea' in content

    def test_lista_ejecuciones_paginacion(self):
        """La lista de ejecuciones pagina correctamente (50 por página)."""
        self.client.login(username='testuser', password='testpass123')
        # Crear 55 ejecuciones
        for i in range(55):
            t = Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': f't{i}'})
            Ejecucion.objects.create(tarea=t, modelo_usado='gemini-flash', tokens_in=10, tokens_out=20, ms=500)
        url = reverse('lista_ejecuciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Página 1 de 2' in content
        # Segunda página
        response = self.client.get(url + '?page=2')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Página 2 de 2' in content

    def test_acciones_lote_ejecuciones_eliminar(self):
        """Acción por lote: eliminar varias ejecuciones."""
        self.client.login(username='testuser', password='testpass123')
        e1 = Ejecucion.objects.create(
            tarea=Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': 'e1'}),
            modelo_usado='gemini-flash', tokens_in=10, tokens_out=20, ms=500,
        )
        e2 = Ejecucion.objects.create(
            tarea=Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': 'e2'}),
            modelo_usado='gemini-flash', tokens_in=10, tokens_out=20, ms=500,
        )
        e3 = Ejecucion.objects.create(
            tarea=Tarea.objects.create(agente=self.agente, habilidad=self.habilidad, estado='ok', payload={'texto': 'e3'}),
            modelo_usado='gemini-flash', tokens_in=10, tokens_out=20, ms=500,
        )
        url = reverse('acciones_lote_ejecuciones')
        response = self.client.post(url, {
            'action': 'eliminar',
            'ejecucion_ids': [e1.pk, e3.pk],
        })
        assert response.status_code == 302
        assert not Ejecucion.objects.filter(pk=e1.pk).exists()
        assert Ejecucion.objects.filter(pk=e2.pk).exists()  # e2 no seleccionada
        assert not Ejecucion.objects.filter(pk=e3.pk).exists()

    def test_design_system_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('design_system')
        response = self.client.get(url)
        assert response.status_code == 200
        html = response.content.decode('utf-8')
        assert 'Sistema de Diseño ARM Flow 2.0' in html
        assert 'btn-primary' in html
        assert 'btn-secondary' in html
        assert 'btn-danger' in html
        assert 'btn-ghost' in html
        assert 'badge badge-success' in html
        assert 'badge badge-error' in html or 'badge badge-danger' in html
        assert 'badge badge-warning' in html
        assert 'badge badge-neutral' in html
        assert 'class="card"' in html
        assert 'class="segmented"' in html

    def test_lista_investigaciones_requiere_login(self):
        """GET a lista_investigaciones sin login redirige a login."""
        url = reverse('lista_investigaciones')
        response = self.client.get(url)
        assert response.status_code == 302

    def test_lista_investigaciones_vacia(self):
        """Lista vacía muestra mensaje y botón de crear."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_investigaciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Fuentes de Monitoreo' in content
        assert 'No hay fuentes de monitoreo todavía' in content
        assert 'Nueva Fuente de Monitoreo' in content
        assert reverse('crear_investigacion') in content

    def test_crear_investigacion_requiere_login(self):
        """GET a crear_investigacion sin login redirige a login."""
        url = reverse('crear_investigacion')
        response = self.client.get(url)
        assert response.status_code == 302

    def test_crear_investigacion_formulario_limpio(self):
        """Formulario de creación muestra 3 campos y control segmentado."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Nuevo Monitoreo de Competencia' in content
        assert 'name="nombre"' in content
        assert 'name="urls_objetivo"' in content
        assert 'name="frecuencia"' in content
        assert 'name="agente"' in content
        assert 'name="palabras_clave"' in content
        assert 'class="segmented"' in content
        assert 'Diaria' in content and 'Semanal' in content and 'Mensual' in content
        assert 'Activar monitoreo' in content
        assert 'btn-primary' in content

    def test_crear_investigacion_con_agente_y_palabras_clave(self):
        """POST con agente y palabras clave guarda los nuevos campos."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        respuesta_publica = [(2, 1, 6, "", ("93.184.216.34", 0))]
        xml_sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://ejemplo.com/pagina-1</loc><lastmod>2024-01-01</lastmod></url>'
            '</urlset>'
        )
        with patch("socket.getaddrinfo", return_value=respuesta_publica), patch(
            "apps.engine.investigaciones.requests.get"
        ) as mock_get:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.text = xml_sitemap
            mock_get.return_value = mock_resp
            response = self.client.post(url, {
                'nombre': 'Monitoreo con Agente',
                'urls_objetivo': 'https://ejemplo.com/sitemap.xml',
                'frecuencia': 'semanal',
                'agente': str(self.agente.pk),
                'palabras_clave': 'seo, competencia, tendencia',
            })
        assert response.status_code == 302
        assert response.url == reverse('lista_investigaciones')
        inv = InvestigacionProgramada.objects.get(nombre='Monitoreo con Agente')
        assert inv.agente_id == self.agente.pk
        assert inv.palabras_clave == 'seo, competencia, tendencia'

    def test_crear_investigacion_guardar_redirige_a_lista(self):
        """POST válido crea la investigación, ejecuta inmediatamente y redirige a la lista."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        respuesta_publica = [(2, 1, 6, "", ("93.184.216.34", 0))]
        xml_sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://ejemplo.com/pagina-1</loc><lastmod>2024-01-01</lastmod></url>'
            '</urlset>'
        )
        with patch("socket.getaddrinfo", return_value=respuesta_publica), patch(
            "apps.engine.investigaciones.requests.get"
        ) as mock_get:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.text = xml_sitemap
            mock_get.return_value = mock_resp
            response = self.client.post(url, {
                'nombre': 'Monitoreo Competencia',
                'urls_objetivo': 'https://ejemplo.com/sitemap.xml\nhttps://otro.com/feed',
                'frecuencia': 'semanal',
            })
        assert response.status_code == 302
        assert response.url == reverse('lista_investigaciones')
        assert InvestigacionProgramada.objects.filter(nombre='Monitoreo Competencia').exists()
        inv = InvestigacionProgramada.objects.get(nombre='Monitoreo Competencia')
        assert inv.frecuencia == 'semanal'
        assert inv.activa is True
        # UX-2A: se ejecuta al crear, por lo que ultima_ejecucion se setea.
        assert inv.ultima_ejecucion is not None

    def test_crear_investigacion_nombre_obligatorio(self):
        """POST sin nombre muestra error de validación."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        response = self.client.post(url, {
            'nombre': '',
            'urls_objetivo': 'https://ejemplo.com/sitemap.xml',
            'frecuencia': 'semanal',
        })
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Este campo es obligatorio.' in content or 'required' in content.lower()
        assert not InvestigacionProgramada.objects.exists()

    def test_lista_investigaciones_muestra_tarjeta(self):
        """Una investigación creada aparece como tarjeta en la lista."""
        InvestigacionProgramada.objects.create(
            nombre='Monitoreo Test',
            urls_objetivo='https://ejemplo.com/sitemap.xml',
            frecuencia='diaria',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        url = reverse('lista_investigaciones')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Monitoreo Test' in content
        assert 'Diaria' in content
        assert 'Activa' in content
        assert 'class="card"' in content

    def test_lista_investigaciones_muestra_acciones_editar_eliminar(self):
        """Cada tarjeta expone enlaces de edición y eliminación."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Con Acciones',
            urls_objetivo='https://ejemplo.com/sitemap.xml',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('lista_investigaciones'))
        content = response.content.decode('utf-8')
        assert reverse('editar_investigacion', args=[inv.pk]) in content
        assert reverse('eliminar_investigacion', args=[inv.pk]) in content
        assert 'enlace-editar' in content
        assert 'form-eliminar' in content
        assert 'btn-danger-sm' in content
        assert 'tabla-acciones' in content

    def test_editar_investigacion_formulario_precargado(self):
        """El formulario de edición carga los datos actuales y cambia sus textos."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Editable',
            urls_objetivo='https://ejemplo.com/feed',
            frecuencia='mensual',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('editar_investigacion', args=[inv.pk])
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Editar Monitoreo de Competencia' in content
        assert 'Guardar cambios' in content
        assert 'Editable' in content
        assert 'https://ejemplo.com/feed' in content
        assert 'value="mensual"' in content

    def test_editar_investigacion_guarda_sin_reejecutar(self):
        """Guardar cambios actualiza el registro y no vuelve a ejecutarlo."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Original',
            urls_objetivo='https://ejemplo.com/feed',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        with patch('apps.panel.views.ejecutar_investigacion') as mock_ejecutar:
            response = self.client.post(
                reverse('editar_investigacion', args=[inv.pk]),
                {
                    'nombre': 'Actualizada',
                    'urls_objetivo': 'https://nuevo.com/rss',
                    'frecuencia': 'diaria',
                },
            )
        assert response.status_code == 302
        assert response.url == reverse('lista_investigaciones')
        inv.refresh_from_db()
        assert inv.nombre == 'Actualizada'
        assert inv.urls_objetivo == 'https://nuevo.com/rss'
        assert inv.frecuencia == 'diaria'
        mock_ejecutar.assert_not_called()

    def test_editar_y_eliminar_investigacion_requieren_login(self):
        """Las acciones de edición y borrado exigen sesión."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Privada',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        response_edit = self.client.get(
            reverse('editar_investigacion', args=[inv.pk])
        )
        response_delete = self.client.post(
            reverse('eliminar_investigacion', args=[inv.pk])
        )
        assert response_edit.status_code == 302
        assert response_delete.status_code == 302
        assert InvestigacionProgramada.objects.filter(pk=inv.pk).exists()

    def test_eliminar_investigacion_solo_post(self):
        """El borrado rechaza GET y conserva el registro."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Solo POST',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('eliminar_investigacion', args=[inv.pk])
        )
        assert response.status_code == 405
        assert InvestigacionProgramada.objects.filter(pk=inv.pk).exists()

    def test_eliminar_investigacion_borra_y_redirige(self):
        """El POST elimina la investigación y sus hallazgos en cascada."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Eliminable',
            urls_objetivo='https://ejemplo.com/sitemap.xml',
            frecuencia='semanal',
            activa=True,
        )
        hallazgo = Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/sitemap.xml',
            tipo_fuente='sitemap',
            titulo='Artículo',
            url_articulo='https://ejemplo.com/articulo',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('eliminar_investigacion', args=[inv.pk])
        )
        assert response.status_code == 302
        assert response.url == reverse('lista_investigaciones')
        assert not InvestigacionProgramada.objects.filter(pk=inv.pk).exists()
        assert not Hallazgo.objects.filter(pk=hallazgo.pk).exists()

    def test_crear_tarea_desde_hallazgo(self):
        """POST crea tarea con payload 'texto' y encola en Huey."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Con Hallazgo',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
            agente=self.agente,
        )
        hallazgo = Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/rss',
            tipo_fuente='rss',
            titulo='Artículo de prueba',
            url_articulo='https://ejemplo.com/articulo',
            contenido_extraido='Texto extraído del artículo.',
        )
        self.client.login(username='testuser', password='testpass123')
        with patch('apps.panel.views.ejecutar_tarea') as mock_ejecutar:
            response = self.client.post(
                reverse('crear_tarea_desde_hallazgo', args=[hallazgo.pk])
            )
        assert response.status_code == 302
        assert response.url == reverse('lista_tareas')

        tarea = Tarea.objects.get(payload__hallazgo_id=hallazgo.pk)
        assert tarea.estado == Tarea.Estado.COLA
        assert tarea.habilidad is not None
        assert tarea.agente == self.agente
        assert tarea.payload['accion'] == 'escribir_desde_hallazgo'
        assert tarea.payload['hallazgo_id'] == hallazgo.pk
        assert tarea.payload['texto'] == 'Artículo de prueba\n\nTexto extraído del artículo.'
        assert 'titulo_base' not in tarea.payload
        assert 'contenido_base' not in tarea.payload
        mock_ejecutar.assert_called_once_with(tarea.pk)

    def test_crear_tarea_desde_hallazgo_idempotente(self):
        """Segundo POST para el mismo hallazgo no crea segunda tarea."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Con Hallazgo',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
            agente=self.agente,
        )
        hallazgo = Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/rss',
            tipo_fuente='rss',
            titulo='Artículo de prueba',
            url_articulo='https://ejemplo.com/articulo',
            contenido_extraido='Texto extraído del artículo.',
        )
        self.client.login(username='testuser', password='testpass123')
        with patch('apps.panel.views.ejecutar_tarea'):
            self.client.post(
                reverse('crear_tarea_desde_hallazgo', args=[hallazgo.pk])
            )
        assert Tarea.objects.filter(payload__hallazgo_id=hallazgo.pk).count() == 1
        with patch('apps.panel.views.ejecutar_tarea') as mock_ejecutar:
            response = self.client.post(
                reverse('crear_tarea_desde_hallazgo', args=[hallazgo.pk])
            )
        assert response.status_code == 302
        assert response.url == reverse('lista_tareas')
        assert Tarea.objects.filter(payload__hallazgo_id=hallazgo.pk).count() == 1
        mock_ejecutar.assert_not_called()
        mensajes = list(messages.get_messages(response.wsgi_request))
        assert any('Ya existe una tarea para este hallazgo' in str(m) for m in mensajes)

    def test_crear_tarea_desde_hallazgo_sin_habilidades(self):
        """Agente sin habilidades muestra error y no crea tarea."""
        agente_sin_habilidades = Agente.objects.create(
            nombre='Sin Habilidades',
            modelo=self.modelo,
            rol='Eres un agente sin habilidades.',
        )
        inv = InvestigacionProgramada.objects.create(
            nombre='Sin Habilidades',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
            agente=agente_sin_habilidades,
        )
        hallazgo = Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/rss',
            tipo_fuente='rss',
            titulo='Artículo de prueba',
            url_articulo='https://ejemplo.com/articulo',
            contenido_extraido='Texto extraído del artículo.',
        )
        self.client.login(username='testuser', password='testpass123')
        with patch('apps.panel.views.ejecutar_tarea') as mock_ejecutar:
            response = self.client.post(
                reverse('crear_tarea_desde_hallazgo', args=[hallazgo.pk])
            )
        assert response.status_code == 302
        assert response.url == reverse('lista_tareas')
        assert not Tarea.objects.filter(payload__hallazgo_id=hallazgo.pk).exists()
        mock_ejecutar.assert_not_called()
        mensajes = list(messages.get_messages(response.wsgi_request))
        assert any('El agente asignado no tiene habilidades configuradas' in str(m) for m in mensajes)

    def test_crear_tarea_bloqueada_en_modo_archivar(self):
        """Modo 'archivar' bloquea creación de tarea desde hallazgo."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Archivar',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
            modo_resultado='archivar',
            agente=self.agente,
        )
        hallazgo = Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/rss',
            tipo_fuente='rss',
            titulo='Artículo de prueba',
            url_articulo='https://ejemplo.com/articulo',
            contenido_extraido='Texto extraído del artículo.',
        )
        self.client.login(username='testuser', password='testpass123')
        with patch('apps.panel.views.ejecutar_tarea') as mock_ejecutar:
            response = self.client.post(
                reverse('crear_tarea_desde_hallazgo', args=[hallazgo.pk])
            )
        # a) NO se crea tarea
        assert not Tarea.objects.filter(payload__hallazgo_id=hallazgo.pk).exists()
        # b) redirige al detalle con 302
        assert response.status_code == 302
        assert response.url == reverse('detalle_investigacion', args=[inv.pk])
        mock_ejecutar.assert_not_called()
        # c) mensaje de warning en la sesión
        mensajes = list(messages.get_messages(response.wsgi_request))
        assert any("modo 'Solo archivar'" in str(m) for m in mensajes)

    def test_detalle_investigacion_muestra_boton_reporte(self):
        """El GET conserva los hallazgos y ofrece el botón de reporte."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Con Reporte',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        Hallazgo.objects.create(
            investigacion=inv,
            url_fuente='https://ejemplo.com/rss',
            tipo_fuente='rss',
            titulo='Hallazgo visible',
            url_articulo='https://ejemplo.com/articulo',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('detalle_investigacion', args=[inv.pk])
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Hallazgo visible' in content
        assert 'Generar Reporte de IA' in content
        assert 'csrfmiddlewaretoken' in content
        assert 'reporte_ia' not in response.context

    def test_detalle_investigacion_requiere_login(self):
        """GET y POST del detalle exigen sesión."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Privada',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        url = reverse('detalle_investigacion', args=[inv.pk])
        assert self.client.get(url).status_code == 302
        assert self.client.post(url).status_code == 302

    def test_detalle_investigacion_post_genera_reporte(self):
        """El POST llama al servicio y renderiza el Markdown como HTML."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Genera Reporte',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        with patch(
            'apps.panel.views.generar_reporte_competencia'
        ) as mock_generar:
            mock_generar.return_value = {
                "reporte": '# Reporte\n\n## Resumen\nTexto **clave**.',
                "artefacto_id": 1,
            }
            response = self.client.post(
                reverse('detalle_investigacion', args=[inv.pk])
            )
        assert response.status_code == 200
        mock_generar.assert_called_once_with(inv.pk)
        assert response.context['reporte_ia'].startswith('# Reporte')
        content = response.content.decode('utf-8')
        assert 'Reporte de Análisis de Competencia' in content
        assert 'class="markdown-content"' in content
        assert '<h1>Reporte</h1>' in content
        assert '<strong>clave</strong>' in content

    def test_detalle_investigacion_post_reporte_vacio_muestra_error(self):
        """Un reporte vacío se trata como error visible en la interfaz."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Reporte Vacío',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        with patch(
            'apps.panel.views.generar_reporte_competencia',
            return_value={"reporte": "", "artefacto_id": None},
        ):
            response = self.client.post(
                reverse('detalle_investigacion', args=[inv.pk])
            )
        assert response.status_code == 200
        assert response.context['error_reporte'] is True
        assert 'reporte_ia' not in response.context
        content = response.content.decode('utf-8')
        assert 'No se pudo generar el reporte. Intenta de nuevo más tarde.' in content

    def test_detalle_investigacion_post_error_no_expone_detalle(self):
        """Un fallo inesperado muestra un mensaje genérico, no la excepción."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Error Interno',
            urls_objetivo='https://ejemplo.com/rss',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        with patch(
            'apps.panel.views.generar_reporte_competencia',
            side_effect=RuntimeError('detalle interno sensible'),
        ):
            response = self.client.post(
                reverse('detalle_investigacion', args=[inv.pk])
            )
        assert response.status_code == 200
        assert response.context['error_reporte'] is True
        assert 'reporte_ia' not in response.context
        content = response.content.decode('utf-8')
        assert 'No se pudo generar el reporte. Intenta de nuevo más tarde.' in content
        assert 'detalle interno sensible' not in content

    def test_crear_investigacion_modo_busqueda_sin_urls(self):
        """POST en modo busqueda con consulta y sin urls_objetivo crea el monitoreo (302)."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        with patch('apps.panel.views.ejecutar_investigacion') as mock_ejecutar:
            mock_ejecutar.return_value = {"hallazgos_nuevos": 0, "fallos": []}
            response = self.client.post(url, {
                'nombre': 'Busqueda Web',
                'modo_busqueda': 'busqueda',
                'consulta_busqueda': 'inteligencia artificial',
                'frecuencia': 'semanal',
            })
        assert response.status_code == 302
        assert response.url == reverse('lista_investigaciones')
        assert InvestigacionProgramada.objects.filter(nombre='Busqueda Web').exists()
        inv = InvestigacionProgramada.objects.get(nombre='Busqueda Web')
        assert inv.modo_busqueda == 'busqueda'
        assert inv.consulta_busqueda == 'inteligencia artificial'
        assert inv.urls_objetivo == ''

    def test_crear_investigacion_modo_sitio_sin_urls_error(self):
        """POST en modo sitio sin urls_objetivo devuelve error de validación en el form."""
        self.client.login(username='testuser', password='testpass123')
        url = reverse('crear_investigacion')
        response = self.client.post(url, {
            'nombre': 'Sitio Sin URLs',
            'modo_busqueda': 'sitio',
            'frecuencia': 'semanal',
        })
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Indica al menos una URL en modo Rastreo de Sitio Web.' in content
        assert not InvestigacionProgramada.objects.exists()

    def test_editar_investigacion_modo_noticias_muestra_ayuda(self):
        """GET del formulario en modo noticias contiene ayuda-noticias y label dinamico."""
        inv = InvestigacionProgramada.objects.create(
            nombre='Noticias Test',
            urls_objetivo='https://ejemplo.com/rss',
            modo_busqueda='noticias',
            consulta_busqueda='pdvsa',
            frecuencia='semanal',
            activa=True,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('editar_investigacion', args=[inv.pk]))
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Vigila las noticias indexadas por Google sobre tu tema.' in content
        assert 'Tema de las noticias a vigilar' in content

    def test_formulario_inicializa_herramientas_segun_modo(self):
        """El formulario preselecciona herramientas de búsqueda según el modo."""
        self.client.login(username='testuser', password='testpass123')
        form = InvestigacionForm(initial={"modo_busqueda": "busqueda"})
        assert form.fields["herramientas_busqueda"].initial == ["ddg_text"]

    def test_biblioteca_renderiza_y_filtra(self):
        """La biblioteca lista hallazgos, filtra por búsqueda y requiere login."""
        investigacion = InvestigacionProgramada.objects.create(
            nombre="Monitoreo Test",
            urls_objetivo="https://ejemplo.com/sitemap.xml",
            frecuencia="semanal",
        )
        Hallazgo.objects.create(
            investigacion=investigacion,
            url_fuente="https://ejemplo.com/sitemap.xml",
            tipo_fuente="sitemap",
            titulo="Noticia sobre python",
            url_articulo="https://ejemplo.com/python",
            fecha_publicacion="2024-01-01",
        )
        Hallazgo.objects.create(
            investigacion=investigacion,
            url_fuente="https://ejemplo.com/sitemap.xml",
            tipo_fuente="sitemap",
            titulo="Noticia sobre java",
            url_articulo="https://ejemplo.com/java",
            fecha_publicacion="2024-01-02",
        )

        # Sin login redirige
        url = reverse("biblioteca")
        response = self.client.get(url)
        assert response.status_code == 302

        self.client.login(username="testuser", password="testpass123")

        # Listado completo muestra ambos hallazgos
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Biblioteca de Descubrimientos" in content
        assert "Noticia sobre python" in content
        assert "Noticia sobre java" in content

        # Filtro por búsqueda: solo el de python aparece
        response = self.client.get(url + "?q=python")
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Noticia sobre python" in content
        assert "Noticia sobre java" not in content