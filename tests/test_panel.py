import pytest
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from apps.core.models import (
    Proveedor, ModeloLLM, Habilidad, Agente, Equipo, Tarea, Artefacto, Ejecucion,
    Workflow, PasoWorkflow,
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
        assert 'Integraciones y API' in content
        assert 'ARM_API_KEY' in content

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