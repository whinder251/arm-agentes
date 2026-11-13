from django.db.models import ProtectedError
from django.test import TestCase

from apps.core.models import (
    Agente,
    Equipo,
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

    def test_crear_equipo_y_asignar_agentes(self):
        agente2 = Agente.objects.create(
            nombre="Agente prueba 2", rol="Rol de prueba 2", modelo=self.modelo
        )
        equipo = Equipo.objects.create(
            nombre="Equipo prueba", descripcion="Equipo de pruebas"
        )
        equipo.agentes.set([self.agente, agente2])

        self.assertEqual(equipo.agentes.count(), 2)
        self.assertIn(equipo, self.agente.equipos.all())
        self.assertIn(equipo, agente2.equipos.all())

    def test_workflow_con_equipo(self):
        equipo = Equipo.objects.create(
            nombre="Equipo workflow", descripcion="Equipo para workflow"
        )
        equipo.agentes.add(self.agente)
        workflow = Workflow.objects.create(
            nombre="Workflow con equipo",
            descripcion="Workflow que usa un equipo",
            equipo=equipo,
        )

        workflow_db = Workflow.objects.get(pk=workflow.pk)
        self.assertEqual(workflow_db.equipo, equipo)
        self.assertIn(workflow_db, equipo.workflows.all())
