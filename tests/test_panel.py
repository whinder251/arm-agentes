import pytest
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