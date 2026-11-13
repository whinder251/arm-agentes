import pytest
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from apps.core.models import Proveedor, ModeloLLM, Habilidad, Agente, Tarea, Artefacto, Ejecucion

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
        enlace = f'href="{reverse("configuracion")}"'
        assert content.count(enlace) == 2
        assert '<a href="#">Proveedores</a>' not in content
        assert '<a href="#">Modelos</a>' not in content

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