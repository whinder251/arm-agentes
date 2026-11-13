from django.db.models import ProtectedError
from django.test import TestCase

from apps.core.models import (
    Agente,
    Habilidad,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Workflow,
)


class TestWorkflow(TestCase):
    def setUp(self):
        self.proveedor = Proveedor.objects.create(
            nombre="Proveedor prueba", base_url="https://ejemplo.com"
        )
        self.modelo = ModeloLLM.objects.create(
            proveedor=self.proveedor, model_id="modelo-test", prioridad=1, activo=True
        )
        self.habilidad = Habilidad.objects.create(
            nombre="Habilidad prueba",
            slug="habilidad-prueba",
            plantilla_prompt="Prompt de prueba",
        )
        self.agente = Agente.objects.create(
            nombre="Agente prueba",
            rol="Rol de prueba",
            modelo=self.modelo,
        )
        self.agente.habilidades.add(self.habilidad)

    def test_crear_workflow_con_pasos(self):
        workflow = Workflow.objects.create(
            nombre="Workflow prueba", descripcion="Un workflow de prueba"
        )
        paso1 = PasoWorkflow.objects.create(
            workflow=workflow,
            orden=1,
            habilidad=self.habilidad,
            agente=self.agente,
            modo_ejecucion="auto",
        )
        paso2 = PasoWorkflow.objects.create(
            workflow=workflow,
            orden=2,
            habilidad=self.habilidad,
            agente=self.agente,
            modo_ejecucion="manual",
        )

        self.assertEqual(workflow.pasos.count(), 2)
        pasos = list(workflow.pasos.all())
        self.assertEqual(pasos[0], paso1)
        self.assertEqual(pasos[1], paso2)

    def test_proteccion_habilidad(self):
        workflow = Workflow.objects.create(nombre="Workflow protegido")
        PasoWorkflow.objects.create(
            workflow=workflow,
            orden=1,
            habilidad=self.habilidad,
            agente=self.agente,
        )

        with self.assertRaises(ProtectedError):
            self.habilidad.delete()
