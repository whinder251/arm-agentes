"""Comando de gestión idempotente para poblar datos de prueba (demo).

Siembra habilidades, agentes, equipos y workflows reutilizando proveedores y
modelos de IA existentes. No crea Proveedor ni ModeloLLM nuevos. Si no existe
ningún proveedor/modelo, aborta con mensaje claro y no crea nada parcial.
"""

import sys

from django.core.management.base import BaseCommand

from apps.core.models import (
    Agente,
    Equipo,
    Habilidad,
    ModeloLLM,
    PasoWorkflow,
    Proveedor,
    Workflow,
)


class Command(BaseCommand):
    help = (
        "Puebla datos de prueba (habilidades, agentes, equipos, workflows) "
        "usando proveedores y modelos existentes (idempotente)."
    )

    def _obtener_modelo(self):
        """Devuelve el primer ModeloLLM cuyo proveedor contenga 'gemini',
        o el primero disponible si no hay coincidencia."""
        modelo = (
            ModeloLLM.objects.select_related("proveedor")
            .filter(proveedor__nombre__icontains="gemini")
            .order_by("pk")
            .first()
        )
        if modelo is None:
            modelo = (
                ModeloLLM.objects.select_related("proveedor")
                .order_by("pk")
                .first()
            )
        return modelo

    def _siembrar_habilidades(self):
        datos = [
            {
                "slug": "investigar_tema",
                "nombre": "Investigar tema",
                "plantilla_prompt": "Investiga a fondo el tema: {{ texto }}",
                "esquema_salida": {},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "redactar_articulo",
                "nombre": "Redactar artículo",
                "plantilla_prompt": "Redacta un artículo basado en: {{ texto }}",
                "esquema_salida": {},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "reescribir_editorial",
                "nombre": "Reescribir editorial",
                "plantilla_prompt": "Reescribe con tono editorial: {{ texto }}",
                "esquema_salida": {},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "revision_calidad",
                "nombre": "Revisión de calidad",
                "plantilla_prompt": "Revisa la calidad de: {{ texto }}",
                "esquema_salida": {},
                "modo_ejecucion": "manual",
            },
            {
                "slug": "metadatos_yoast",
                "nombre": "Metadatos Yoast",
                "plantilla_prompt": "Genera metadatos SEO para: {{ texto }}",
                "esquema_salida": {"titulo": "", "descripcion": "", "keyword": ""},
                "modo_ejecucion": "auto",
            },
        ]
        creadas = 0
        existentes = 0
        for d in datos:
            obj, created = Habilidad.objects.get_or_create(
                slug=d["slug"], defaults=d
            )
            if created:
                creadas += 1
            else:
                existentes += 1
        return creadas, existentes

    def _siembrar_agentes(self, modelo):
        datos = [
            {"nombre": "Investigador", "rol": "Eres un investigador experto.", "temperatura": 0.5},
            {"nombre": "Redactor", "rol": "Eres un redactor experto.", "temperatura": 0.7},
            {"nombre": "Editor", "rol": "Eres un editor experto.", "temperatura": 0.6},
            {"nombre": "Optimizador SEO", "rol": "Eres un experto en SEO.", "temperatura": 0.4},
        ]
        creados = 0
        existentes = 0
        for d in datos:
            obj, created = Agente.objects.get_or_create(
                nombre=d["nombre"],
                defaults={"rol": d["rol"], "temperatura": d["temperatura"], "modelo": modelo},
            )
            if created:
                creados += 1
            else:
                existentes += 1
        return creados, existentes

    def _siembrar_equipos(self):
        datos = [
            {"nombre": "Contenido Web", "descripcion": "Equipo para contenido web."},
            {"nombre": "Adaptacion", "descripcion": "Equipo para adaptacion de contenido."},
        ]
        creados = 0
        existentes = 0
        for d in datos:
            obj, created = Equipo.objects.get_or_create(
                nombre=d["nombre"], defaults={"descripcion": d["descripcion"]}
            )
            if created:
                creados += 1
            else:
                existentes += 1
        return creados, existentes

    def _siembrar_workflows(self):
        datos = [
            {
                "nombre": "Publicacion de articulos",
                "descripcion": "Flujo completo de investigacion y publicacion.",
                "pasos": [
                    {"orden": 1, "habilidad_slug": "investigar_tema", "modo_ejecucion": "auto"},
                    {"orden": 2, "habilidad_slug": "redactar_articulo", "modo_ejecucion": "auto"},
                    {"orden": 3, "habilidad_slug": "revision_calidad", "modo_ejecucion": "manual"},
                ],
            },
            {
                "nombre": "Adaptacion de contenido",
                "descripcion": "Flujo de reescritura y optimizacion SEO.",
                "pasos": [
                    {"orden": 1, "habilidad_slug": "reescribir_editorial", "modo_ejecucion": "auto"},
                    {"orden": 2, "habilidad_slug": "metadatos_yoast", "modo_ejecucion": "auto"},
                ],
            },
        ]
        creados = 0
        existentes = 0
        for d in datos:
            workflow, created = Workflow.objects.get_or_create(
                nombre=d["nombre"],
                defaults={"descripcion": d["descripcion"], "estado": "borrador"},
            )
            if created:
                creados += 1
            else:
                existentes += 1
            for paso in d["pasos"]:
                habilidad = Habilidad.objects.filter(slug=paso["habilidad_slug"]).first()
                if habilidad is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Saltando paso '{paso['habilidad_slug']}': habilidad no encontrada."
                        )
                    )
                    continue
                PasoWorkflow.objects.get_or_create(
                    workflow=workflow,
                    orden=paso["orden"],
                    defaults={
                        "habilidad": habilidad,
                        "agente": None,
                        "modo_ejecucion": paso["modo_ejecucion"],
                    },
                )
        return creados, existentes

    def handle(self, *args, **options):
        modelo = self._obtener_modelo()
        if modelo is None:
            self.stdout.write(
                self.style.ERROR(
                    "No existe ningun Proveedor/ModeloLLM disponible. "
                    "Crea al menos uno antes de ejecutar seed_demo."
                )
            )
            sys.exit(1)

        self.stdout.write(
            self.style.NOTICE(
                f"Usando modelo: {modelo.proveedor.nombre} / {modelo.model_id}"
            )
        )

        h_creadas, h_exist = self._siembrar_habilidades()
        a_creados, a_exist = self._siembrar_agentes(modelo)
        e_creados, e_exist = self._siembrar_equipos()
        w_creados, w_exist = self._siembrar_workflows()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Resumen de seed_demo:"))
        self.stdout.write(f"  Habilidades: {h_creadas} creadas, {h_exist} ya existían.")
        self.stdout.write(f"  Agentes: {a_creados} creados, {a_exist} ya existían.")
        self.stdout.write(f"  Equipos: {e_creados} creados, {e_exist} ya existían.")
        self.stdout.write(f"  Workflows: {w_creados} creados, {w_exist} ya existían.")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed completado (idempotente)."))
