# Roadmap de ARM — Pasos 15 a 20

## Paso 15: Cimientos de Producción
**Objetivo:** Implementar reglas de negocio críticas aprobadas.
**Archivos:** apps/core/models.py, apps/panel/forms.py, apps/panel/views.py, apps/panel/templates/panel/*.html
**Criterio:**
- Campo api_key cifrado en Proveedor (usar cryptography)
- Campo modo_ejecucion ('auto', 'manual') en Habilidad
- Campo limite_tokens_diario en Proveedor
- Validación de cuota antes de encolar
- Confirmación de borrado en botones Eliminar (onclick="return confirm(...)")
- Tests en verde
**Requisitos:** RF-SEC-001, RF-BUD-002, RB-009, RB-013, RB-014

## Paso 16: Modelo Workflow y PasoWorkflow
**Objetivo:** Crear estructura para flujos de trabajo multi-paso.
**Archivos:** apps/core/models.py, apps/core/migrations/, tests/test_workflow.py
**Criterio:**
- Modelo Workflow (nombre, descripción, equipo FK opcional, estado)
- Modelo PasoWorkflow (orden, workflow FK, habilidad FK, agente FK, modo_ejecucion)
- Al crear Workflow, generar Tarea por cada PasoWorkflow encadenadas
- Tests en verde
**Requisitos:** RF-TSK-006, RF-TSK-007, RB-011

## Paso 17: UI de Flujos de Trabajo
**Objetivo:** Interfaz para crear, editar y visualizar pipelines.
**Archivos:** apps/panel/views.py, apps/panel/urls.py, apps/panel/templates/panel/workflow_*.html
**Criterio:**
- Listado de Workflows con estado
- Formulario para crear Workflow con pasos dinámicos (añadir/eliminar pasos)
- Cada paso muestra habilidad, agente, modo_ejecucion
- Botón "Ejecutar Workflow" que encola el primer paso
- Tests en verde
**Requisitos:** RF-TSK-006, RF-TSK-007

## Paso 18: Orquestador de Equipos
**Objetivo:** Asignar Workflows a equipos de agentes.
**Archivos:** apps/core/models.py, apps/agents/views.py, apps/panel/templates/panel/equipo_*.html
**Criterio:**
- Modelo Equipo (nombre, descripción)
- Relación M2M Equipo-Agente
- Workflow puede asignarse a Equipo en lugar de agente individual
- Orquestador elige agente del equipo según disponibilidad y habilidades
- Tests en verde
**Requisitos:** RF-AGT-007, RF-AGT-008, RB-012

## Paso 19: API REST para Integraciones
**Objetivo:** Exponer endpoints para sistemas externos.
**Archivos:** apps/api/views.py, apps/api/urls.py, apps/api/serializers.py, apps/api/tests.py
**Criterio:**
- Endpoint POST /api/v1/webhook/tarea/ para crear tarea desde externo
- Endpoint GET /api/v1/tarea/<pk>/ para consultar estado
- Autenticación con token en header
- Validación de payload con Pydantic
- Tests en verde (sin llamar APIs reales)
**Requisitos:** RF-INT-001, RF-INT-002, RF-SEC-003, RB-017

## Paso 20: Plugin WordPress (Proyecto Paralelo)
**Objetivo:** Plugin que consume API de ARM para generar datos SEO.
**Archivos:** (repo separado) plugin-wordpress-arm/
**Criterio:**
- Plugin añade metabox en editor de WordPress
- Al guardar borrador, envía contenido a ARM vía API
- ARM devuelve título SEO, meta descripción, frase enfoque, metaetiquetas
- Plugin inyecta datos en campos de Yoast/RankMath
- Documentación de instalación
**Requisitos:** RF-INT-003, RF-PUB-003, RB-019

## Dependencias entre pasos
- Paso 15 es independiente (cimientos)
- Paso 16 depende de Paso 15 (necesita modelos estables)
- Paso 17 depende de Paso 16 (UI sobre modelos Workflow)
- Paso 18 depende de Paso 16 (orquestador usa Workflow)
- Paso 19 depende de Paso 15 (API necesita seguridad)
- Paso 20 depende de Paso 19 (plugin consume API)

## Estado Actual
- Pasos 0-14: COMPLETADOS (panel funcional, diseño Apple/SaaS, creación de tareas)
- Paso 15: PENDIENTE (cimientos de producción)
- Pasos 16-20: PLANIFICADOS