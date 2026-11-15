"""Comando de gestión idempotente para poblar datos de prueba (demo).

Siembra habilidades, agentes, equipos y workflows reutilizando proveedores y
modelos de IA existentes. No crea Proveedor ni ModeloLLM nuevos. Si no existe
ningún proveedor/modelo, aborta con mensaje claro y no crea nada parcial.

Es idempotente: al ejecutarse varias veces no duplica registros. Si un Equipo
ya existe pero no tiene agentes vinculados, se le añaden. Si un PasoWorkflow
ya existe pero tiene agente=None, se le asigna el agente correcto.
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
                "plantilla_prompt": "Investiga a fondo el tema: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título del tema investigado\",\n  \"slug\": \"slug-del-tema\",\n  \"contenido": "Cuerpo del informe de investigación en markdown\",\n  \"meta_description\": \"Resumen de 150-160 caracteres para SEO\",\n  \"focus_keyword\": \"palabra clave principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "redactar_articulo",
                "nombre": "Redactar artículo",
                "plantilla_prompt": "Redacta un artículo basado en: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título atractivo del artículo\",\n  \"slug\": \"titulo-atractivo-del-articulo\",\n  \"contenido": "Cuerpo del artículo en markdown, con H2 y H3\",\n  \"meta_description\": \"Descripción de 150-160 caracteres para SEO\",\n  \"focus_keyword\": \"palabra clave principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "reescribir_editorial",
                "nombre": "Reescribir editorial",
                "plantilla_prompt": "Reescribe con tono editorial: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título reescrito\",\n  \"slug\": \"titulo-reescrito\",\n  \"contenido": "Texto reescrito con tono editorial\",\n  \"meta_description\": \"Descripción de 150-160 caracteres para SEO\",\n  \"focus_keyword\": \"palabra clave principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "revision_calidad",
                "nombre": "Revisión de calidad",
                "plantilla_prompt": "Revisa la calidad de: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Informe de revisión\",\n  \"slug\": \"informe-revision\",\n  \"contenido": "Observaciones y sugerencias de mejora en markdown\",\n  \"meta_description\": \"Resumen de la revisión de calidad\",\n  \"focus_keyword\": \"calidad\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "manual",
            },
            {
                "slug": "metadatos_yoast",
                "nombre": "Metadatos Yoast",
                "plantilla_prompt": "Genera metadatos SEO para: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título SEO optimizado\",\n  \"slug\": \"titulo-seo-optimizado\",\n  \"contenido": "Texto optimizado para SEO\",\n  \"meta_description\": \"Descripción meta de 150-160 caracteres\",\n  \"focus_keyword\": \"palabra clave principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "corregir_ortografia",
                "nombre": "Corregir ortografía",
                "plantilla_prompt": "Corrige faltas de ortografía: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Texto corregido\",\n  \"slug\": \"texto-corregido\",\n  \"contenido": "Texto con la ortografía corregida\",\n  \"meta_description\": \"Resumen del texto corregido\",\n  \"focus_keyword\": \"ortografía\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "optimizar_seo",
                "nombre": "Optimizar SEO",
                "plantilla_prompt": "Optimiza para SEO: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título optimizado para SEO\",\n  \"slug\": \"titulo-seo\",\n  \"contenido": "Texto optimizado para motores de búsqueda\",\n  \"meta_description\": \"Descripción meta optimizada\",\n  \"focus_keyword\": \"palabra clave principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "crear_titular",
                "nombre": "Crear titular",
                "plantilla_prompt": "Crea un titular atractivo para: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Titular atractivo\",\n  \"slug\": \"titular-atractivo\",\n  \"contenido": "Desarrollo del titular en una frase\",\n  \"meta_description\": \"Descripción corta del titular\",\n  \"focus_keyword\": \"palabra clave del titular\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "resumir_contenido",
                "nombre": "Resumir contenido",
                "plantilla_prompt": "Resume el contenido: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Resumen\",\n  \"slug\": \"resumen-contenido\",\n  \"contenido": "Resumen del contenido en markdown\",\n  \"meta_description\": \"Resumen ejecutivo de 150-160 caracteres\",\n  \"focus_keyword\": \"tema principal\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "manual",
            },
            {
                "slug": "traducir_texto",
                "nombre": "Traducir texto",
                "plantilla_prompt": "Traduce al inglés: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título traducido\",\n  \"slug\": \"titulo-traducido\",\n  \"contenido": "Texto traducido al inglés\",\n  \"meta_description\": \"Descripción de la traducción\",\n  \"focus_keyword\": \"traducción\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "generar_meta_descripcion",
                "nombre": "Generar meta descripción",
                "plantilla_prompt": "Genera meta descripción para: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Título para meta\",\n  \"slug\": \"titulo-para-meta\",\n  \"contenido": "Contenido base para la meta descripción\",\n  \"meta_description\": \"Descripción meta de 150-160 caracteres\",\n  \"focus_keyword\": \"palabra clave para meta\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "auto",
            },
            {
                "slug": "revisar_estilo",
                "nombre": "Revisar estilo",
                "plantilla_prompt": "Revisa el estilo y tono: {{ texto }}\n\nResponde ÚNICAMENTE con un objeto JSON válido con esta estructura:\n{\n  \"titulo\": \"Informe de estilo\",\n  \"slug\": \"informe-estilo\",\n  \"contenido": "Comentarios sobre estilo y tono en markdown\",\n  \"meta_description\": \"Resumen de la revisión de estilo\",\n  \"focus_keyword\": \"estilo\"\n}\n\nNo incluyas texto fuera del JSON. No uses bloques de código markdown.",
                "esquema_salida": {"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""},
                "modo_ejecucion": "manual",
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
                for campo, valor in d.items():
                    setattr(obj, campo, valor)
                obj.save()
                existentes += 1
        return creadas, existentes

    def _siembrar_agentes(self, modelo):
        # nombre -> {rol, temperatura, [slugs de habilidades]}
        datos = {
            "Investigador": {
                "rol": "Eres un investigador experto.",
                "temperatura": 0.5,
                "habilidades": ["investigar_tema", "resumir_contenido"],
            },
            "Redactor": {
                "rol": "Eres un redactor experto.",
                "temperatura": 0.7,
                "habilidades": ["redactar_articulo", "crear_titular"],
            },
            "Editor": {
                "rol": "Eres un editor experto.",
                "temperatura": 0.6,
                "habilidades": ["revision_calidad", "revisar_estilo"],
            },
            "SEO": {
                "rol": "Eres un experto en SEO.",
                "temperatura": 0.4,
                "habilidades": [
                    "optimizar_seo",
                    "metadatos_yoast",
                    "generar_meta_descripcion",
                ],
            },
            "Ortografia": {
                "rol": "Eres un corrector de ortografía.",
                "temperatura": 0.3,
                "habilidades": ["corregir_ortografia"],
            },
            "Traductor": {
                "rol": "Eres un traductor experto.",
                "temperatura": 0.5,
                "habilidades": ["traducir_texto"],
            },
        }
        habilidades = {h.slug: h for h in Habilidad.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            obj, created = Agente.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "rol": d["rol"],
                    "temperatura": d["temperatura"],
                    "modelo": modelo,
                },
            )
            if created:
                creados += 1
            else:
                obj.rol = d["rol"]
                obj.temperatura = d["temperatura"]
                obj.modelo = modelo
                obj.save()
                existentes += 1
            obj.habilidades.set(
                [habilidades[s] for s in d["habilidades"] if s in habilidades]
            )
        return creados, existentes

    def _siembrar_equipos(self):
        # nombre -> {descripcion, [nombres de agentes]}
        datos = {
            "Editorial": {
                "descripcion": "Equipo de creación y revisión de contenido editorial.",
                "agentes": ["Investigador", "Redactor", "Editor"],
            },
            "Marketing": {
                "descripcion": "Equipo de contenidos de marketing y SEO.",
                "agentes": ["Redactor", "SEO", "Traductor"],
            },
            "Soporte": {
                "descripcion": "Equipo de soporte y corrección de contenidos.",
                "agentes": ["Investigador", "Ortografia", "Redactor"],
            },
        }
        agentes = {a.nombre: a for a in Agente.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            obj, created = Equipo.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": d["descripcion"]},
            )
            if created:
                creados += 1
            else:
                obj.descripcion = d["descripcion"]
                obj.save()
                existentes += 1
            obj.agentes.set(
                [agentes[a] for a in d["agentes"] if a in agentes]
            )
        return creados, existentes

    def _siembrar_workflows(self):
        # nombre -> {descripcion, equipo, [(orden, slug_habilidad, nombre_agente, modo)]}
        datos = {
            "Publicacion de articulos": {
                "descripcion": "Flujo completo de investigacion y publicacion.",
                "equipo": "Editorial",
                "pasos": [
                    (1, "investigar_tema", "Investigador", "auto"),
                    (2, "redactar_articulo", "Redactor", "auto"),
                    (3, "revisar_estilo", "Editor", "manual"),
                    (4, "metadatos_yoast", "SEO", "auto"),
                ],
            },
            "Adaptacion de contenido": {
                "descripcion": "Flujo de reescritura y optimizacion SEO.",
                "equipo": "Marketing",
                "pasos": [
                    (1, "reescribir_editorial", "Redactor", "auto"),
                    (2, "traducir_texto", "Traductor", "auto"),
                    (3, "optimizar_seo", "SEO", "auto"),
                ],
            },
            "Revision de calidad": {
                "descripcion": "Flujo de correccion y revision final.",
                "equipo": "Editorial",
                "pasos": [
                    (1, "corregir_ortografia", "Ortografia", "auto"),
                    (2, "revision_calidad", "Editor", "manual"),
                ],
            },
            "Creacion de titulares y SEO": {
                "descripcion": "Flujo de titulares y metadatos SEO.",
                "equipo": "Marketing",
                "pasos": [
                    (1, "crear_titular", "Redactor", "auto"),
                    (2, "generar_meta_descripcion", "SEO", "auto"),
                ],
            },
        }
        habilidades = {h.slug: h for h in Habilidad.objects.all()}
        agentes = {a.nombre: a for a in Agente.objects.all()}
        equipos = {e.nombre: e for e in Equipo.objects.all()}
        creados = 0
        existentes = 0
        for nombre, d in datos.items():
            equipo = equipos.get(d["equipo"])
            workflow, created = Workflow.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "descripcion": d["descripcion"],
                    "estado": "borrador",
                    "equipo": equipo,
                },
            )
            if created:
                creados += 1
            else:
                workflow.descripcion = d["descripcion"]
                workflow.equipo = equipo
                workflow.estado = "borrador"
                workflow.save()
                existentes += 1
            for orden, slug_habilidad, nombre_agente, modo in d["pasos"]:
                habilidad = habilidades.get(slug_habilidad)
                agente = agentes.get(nombre_agente)
                if habilidad is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Saltando paso {orden} de '{nombre}': "
                            f"habilidad '{slug_habilidad}' no encontrada."
                        )
                    )
                    continue
                PasoWorkflow.objects.update_or_create(
                    workflow=workflow,
                    orden=orden,
                    defaults={
                        "habilidad": habilidad,
                        "agente": agente,
                        "modo_ejecucion": modo,
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
