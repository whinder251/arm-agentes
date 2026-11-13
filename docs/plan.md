# Plan de construcción — ARM

## Estado Actual (2026-11-14)
**Pasos 0 a 21 COMPLETADOS.** 
El sistema cuenta con: panel web estilo Apple/SaaS, creación de tareas con asignación automática, modelos Workflow/PasoWorkflow/Equipo, API REST con Pydantic v2, publicación en WordPress (borradores), cifrado de API keys y validación de cuotas.
*Ver `docs/plan_historial.md` para el registro detallado de evidencias de los pasos 0-20.*

## Reglas de Ejecución (NO ROMPER)
1. **Máximo 4 archivos** por paso (excepción autorizada solo si se explicita).
2. **PowerShell 5.1**: Usar `.venv\Scripts\python.exe` línea por línea. **PROHIBIDO usar `&&`**.
3. **NO ejecutar `git push`** desde el agente. El usuario lo hace manualmente por autenticación.
4. **Tests**: Siempre en verde antes de cerrar. Usar `respx` y fixtures. Cero llamadas a APIs reales.
5. **Diseño UI**: Estilo Apple/SaaS estricto (#F5F5F7, #FFFFFF, #D2D2D7, #0071E3). CERO fondos crema, CERO emojis como iconos.

## Paso 21 (COMBINADO) — COMPLETADO
**Objetivo:** 
1) Orquestación: Ejecutar Workflows paso a paso. Al terminar un paso en 'ok', encolar el siguiente automáticamente.
2) Conteo real: Actualizar `tokens_consumidos_hoy` del Proveedor con los tokens reales de cada ejecución.

**Archivos tocados:**
- `apps/core/models.py`: FK `paso_workflow` en `Tarea` (SET_NULL, related_name='tareas').
- `apps/engine/tasks.py`: conteo de tokens en `ejecutar_tarea` (suma segura `(tokens_in or 0) + (tokens_out or 0)` sobre `proveedor.tokens_consumidos_hoy`), orquestación al final de `ejecutar_tarea` que llama `continuar_workflow.delay(...)` cuando `estado == 'ok'` y hay `paso_workflow`, y nueva tarea `@db_task() continuar_workflow(workflow_id, siguiente_orden)` que avanza al siguiente paso o marca el workflow como 'completado'.
- `apps/panel/views.py`: vista `ejecutar_workflow` (`@login_required`, `@require_POST`), valida estado 'borrador', lo pasa a 'en_ejecucion' y encola `continuar_workflow.delay(workflow.pk, 1)`.
- `apps/panel/urls.py`: ruta `workflows/<int:pk>/ejecutar/`.
- `apps/panel/templates/panel/lista_workflows.html`: botón "Ejecutar" (#34C759) solo si `estado == 'borrador'`.
- `tests/test_workflow.py`: `test_orquestacion_workflow`.
- Migración generada y aplicada: `apps/core/migrations/0010_tarea_paso_workflow.py`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py makemigrations core` → migración `0010_tarea_paso_workflow` creada.
- `.venv\Scripts\python.exe manage.py migrate` → `Applying core.0010_tarea_paso_workflow... OK`.
- `.venv\Scripts\python.exe -m pytest tests/test_workflow.py -q` → `5 passed in 1.74s`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.

Un Workflow con 2 pasos encadena paso 1 ('ok') → paso 2 creado, vinculado al `PasoWorkflow` y encolado; los tokens reales se suman al proveedor; `pytest` y `manage.py check` en verde.

## Paso 22a - Reorganización del sidebar — COMPLETADO

**Objetivo:** Hacer visibles todas las funciones ya implementadas (Workflows, Equipos) y agrupar el menú del sidebar por intención, sin tocar lógica de vistas.

**Archivos tocados:**
- `apps/panel/templates/panel/base.html`: reemplazo del bloque `<nav>` del sidebar por dos secciones con encabezados de texto (no enlaces): "Operación" (Tareas, Workflows, Equipos) y "Configuración" (Agentes, Habilidades, Modelos y proveedores). Encabezados con estilo Apple (font-size 0.7rem, letter-spacing 0.05em, color #6E6E73, font-weight 600, text-transform uppercase, padding 4px 0). Enlace activo resaltado con color #0071E3 y fondo rgba(0,113,227,0.08) usando `request.resolver_match.url_name`. Botón Logout mantenido al final.
- `tests/test_panel.py`: prueba `test_sidebar_contiene_workflows_y_equipos` que verifica presencia de enlaces a lista_workflows y lista_equipos y los textos "Workflows" y "Equipos". Ajuste de `test_sidebar_enlaza_configuracion` (1 enlace a configuracion tras agrupar Proveedores/Modelos).
- `docs/plan.md`: esta sección.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "sidebar" -q` → `2 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `21 passed`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.

Sidebar reorganizado por secciones sin tocar vistas; paleta, radios, tipografía y glassmorphism del sidebar sin cambios.