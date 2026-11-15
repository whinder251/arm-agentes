import pytest
from unittest.mock import Mock, patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from apps.core.models import (
    Proveedor, ModeloLLM, Habilidad, Agente, Equipo, Tarea, Artefacto, Ejecucion,
    Workflow, PasoWorkflow, DestinoPublicacion, IntegracionConfig,
)

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
            plantilla_prompt='test', 
            esquema_salida={}
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
        assert f'href="{reverse("lista_proveedores")}"' in content
        assert f'href="{reverse("lista_modelos")}"' in content
        assert 'Proveedores' in content
        assert 'Modelos' in content
        assert 'Modelos y proveedores' not in content

    def test_dashboard_render(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('dashboard')
        response = self.client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Tareas en Cola' in content
        assert 'Tokens Consumidos Hoy' in content
        assert 'Workflows Activos' in content

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
            plantilla_prompt='test seo',
            esquema_salida={}
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
            plantilla_prompt='test seo',
            esquema_salida={}
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
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'http://wp.test.invalid/123'
            response = self.client.post(url)

        assert response.status_code == 302
        assert response.url == reverse('detalle_tarea', args=[tarea.pk])
        instance.crear_borrador.assert_called_once()
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

    def test_publicar_tarea_sin_destino_no_expone_api_key_proveedor(self):
        """Fallback al Proveedor LLM sin exponer su api_key en payload ni mensajes."""
        proveedor_wp = Proveedor.objects.create(
            nombre='wordpress-fallback',
            api_key='usuario-fallback:secreto-fallback-12345',
            base_url='http://wp-fallback.test.invalid',
        )
        modelo_wp = ModeloLLM.objects.create(
            proveedor=proveedor_wp, model_id='wp-modelo-fallback'
        )
        agente_wp = Agente.objects.create(
            nombre='Agente WP Fallback', modelo=modelo_wp, rol='Publicador'
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
            instance = mock_wp.return_value
            instance.crear_borrador.return_value = 'http://wp-fallback.test.invalid/456'
            response = self.client.post(url)  # sin destino_id

        assert response.status_code == 302
        assert response.url == reverse('detalle_tarea', args=[tarea.pk])
        # Usa el proveedor LLM como fallback
        mock_wp.assert_called_once_with(
            api_key='usuario-fallback:secreto-fallback-12345',
            base_url='http://wp-fallback.test.invalid',
        )
        tarea.refresh_from_db()
        assert tarea.payload.get('wordpress_link') == 'http://wp-fallback.test.invalid/456'
        assert tarea.payload.get('enviado_a_wordpress') is True
        # El api_key del proveedor LLM no debe persistirse en el payload
        assert 'secreto-fallback-12345' not in str(tarea.payload)
        # Tampoco en el cuerpo de la respuesta
        assert 'secreto-fallback-12345' not in response.content.decode('utf-8', errors='ignore')

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
        assert 'href="{}"'.format(reverse('lista_workflows')) in content
        assert 'href="{}"'.format(reverse('lista_equipos')) in content
        assert 'Workflows' in content
        assert 'Equipos' in content

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
            plantilla_prompt='test',
            esquema_salida={},
        )
        nueva_h2 = Habilidad.objects.create(
            nombre='Redacción',
            slug='redaccion',
            plantilla_prompt='test',
            esquema_salida={},
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
        assert 'Cambiar API key' in content

    def test_editar_proveedor_no_cambiar_api_key_conserva_clave(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        clave_original = self.proveedor.api_key
        response = self.client.post(url, {
            'nombre': 'gemini-editado',
            'base_url': 'http://editado.invalid',
            'api_key': '****fake',
            'rpm': '100',
            'limite_diario': '1000',
        })
        assert response.status_code == 302
        assert response.url == reverse('lista_proveedores')
        self.proveedor.refresh_from_db()
        assert self.proveedor.api_key == clave_original

    def test_editar_proveedor_cambiar_api_key_actualiza_clave(self):
        self.client.login(username='testuser', password='testpass123')
        url = reverse('editar_proveedor', args=[self.proveedor.pk])
        nueva_clave = 'sk-nueva-clave-secreta-1234'
        response = self.client.post(url, {
            'nombre': 'gemini-editado',
            'base_url': 'http://editado.invalid',
            'cambiar_api_key': 'on',
            'nueva_api_key': nueva_clave,
            'rpm': '100',
            'limite_diario': '1000',
        })
        assert response.status_code == 302
        assert response.url == reverse('lista_proveedores')
        self.proveedor.refresh_from_db()
        assert self.proveedor.api_key == nueva_clave

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