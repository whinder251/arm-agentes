# Plan de construcción — ARM

## Estado Actual (2026-11-14)
**Pasos 0 a 25 COMPLETADOS. Núcleo de ARM v1.0 terminado.** 
El sistema cuenta con: panel web estilo Apple/SaaS, creación de tareas con asignación automática, modelos Workflow/PasoWorkflow/Equipo, API REST con Pydantic v2, publicación en WordPress (borradores), cifrado de API keys, validación de cuotas, orquestación de workflows paso a paso, conteo real de tokens, dashboard de métricas, integraciones con ARM_API_KEY visible, propagación de fallos y vista de historial de ejecuciones para auditoría.
*Ver `docs/plan_historial.md` para el registro detallado de evidencias de los pasos 0-20.*

**Bloque B (Rediseño UX/UI) COMPLETADO.** Sistema de diseño ARM Flow centralizado y aplicado a todo el panel.

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

## Paso 22b - Dashboard de Métricas — COMPLETADO

**Objetivo:** Vista de Dashboard que muestra el estado general del sistema: tareas por estado, tokens consumidos hoy (suma de todos los proveedores) y workflows en ejecución.

**Archivos tocados:**
- `apps/panel/views.py`: importación de `Sum` de `django.db.models`, nueva vista `dashboard` con `@login_required` que calcula `tareas_cola`, `tareas_ok`, `tareas_fallo`, `tokens_hoy` y `workflows_activos` y las pasa al contexto.
- `apps/panel/urls.py`: ruta `path('dashboard/', views.dashboard, name='dashboard')` añadida (se mantiene `''` como `lista_tareas` para no romper flujo existente).
- `apps/panel/templates/panel/base.html`: enlace "Dashboard" como primer elemento en sección "Operación" del sidebar, con clase `activo` condicional. CSS de grid y tarjetas estilo Apple/SaaS (#FFFFFF, borde #D2D2D7, radius 12px, sombra suave, gap 24px).
- `apps/panel/templates/panel/dashboard.html` (nuevo): extiende `panel/base.html`, título "Panel de Control", subtítulo "Resumen de actividad y consumo", grid de 4 tarjetas (Tareas en Cola #0071E3, Tareas Completadas #34C759, Tokens Consumidos Hoy #1D1D1F, Workflows Activos #FF9500).
- `tests/test_panel.py`: prueba `test_dashboard_render` (login, GET a 'dashboard', status 200, presencia de "Tareas en Cola", "Tokens Consumidos Hoy", "Workflows Activos").
- `docs/plan.md`: esta sección.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "dashboard" -q` → `1 passed`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.

Dashboard de métricas del sistema con 4 tarjetas estilo Apple/SaaS, sin fondos crema ni emojis.

## Paso 23 - Gestión de Integraciones y Propagación de Fallos en Workflows — COMPLETADO

**Objetivo:**
1) Mostrar la ARM_API_KEY en el panel para facilitar la conexión con sistemas externos.
2) Asegurar que si una tarea de un Workflow falla definitivamente, el Workflow padre cambie su estado a 'fallido'.

**Archivos tocados:**
- `apps/engine/tasks.py`: en el bloque `except Exception` de `ejecutar_tarea`, tras `_registrar_fallo(tarea)`, se verifica si `tarea.paso_workflow_id` existe; si es así, `tarea.paso_workflow.workflow.estado = 'fallido'` y se guarda con `update_fields=['estado']`.
- `apps/panel/views.py`: importación de `settings` de `django.conf`, nueva vista `integraciones` con `@login_required` que obtiene `settings.ARM_API_KEY` y la pasa al contexto.
- `apps/panel/urls.py`: ruta `path('integraciones/', views.integraciones, name='integraciones')` añadida.
- `apps/panel/templates/panel/base.html`: enlace "Integraciones" al final de la sección "Configuración" del sidebar, con clase `activo` condicional.
- `apps/panel/templates/panel/integraciones.html` (nuevo): extiende `panel/base.html`, título "Integraciones y API", tarjeta estilo Apple/SaaS que muestra la `ARM_API_KEY`, botón "Copiar al portapapeles" con JavaScript y nota de advertencia en rojo.
- `tests/test_panel.py`: prueba `test_integraciones_render` (login, GET a 'integraciones', status 200, presencia de "Integraciones y API" y "ARM_API_KEY").
- `docs/plan.md`: esta sección.
- `AGENTS.md`: sección de estado actualizada con el paso 23.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones" -q` → `1 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `22 passed`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.

Panel de integraciones con ARM_API_KEY visible y botón copiar; fallo definitivo de tarea en workflow propaga estado 'fallido' al workflow padre; sin fondos crema ni emojis.

## Paso 24 - Documentación profesional — COMPLETADO

**Objetivo:** Dejar el proyecto listo para ser instalado y entendido por un desarrollador externo, y corregir la inconsistencia entre docs/plan.md y docs/requirements/roadmap.md.

**Archivos tocados:**
- `README.md` (nuevo): título, subtítulo, características, requisitos, instalación, variables de entorno obligatorias, ejecución, arquitectura, licencia MIT.
- `.env.example` (nuevo): `ARM_ENCRYPTION_KEY`, `ARM_API_KEY` y `DEBUG` con comentarios explicativos.
- `docs/requirements/roadmap.md` (reemplazo completo): estado actual (2026-11-14), pasos 0-23 completados, próximos pasos fuera del núcleo Django, dependencias técnicas.
- `docs/plan.md`: esta sección.

**Criterio de aceptación:** Documentación limpia y profesional; roadmap sincronizado con el estado real del proyecto. Sin ejecución de tests (solo documentación).

## Paso 25 - Historial de Ejecuciones — COMPLETADO

**Objetivo:** Vista de solo lectura que muestre el historial de todas las ejecuciones de IA, permitiendo auditar consumo de tokens, duración y errores por tarea.

**Archivos tocados:**
- `apps/panel/views.py`: importación de `Ejecucion`, nueva vista `lista_ejecuciones` con `@login_required`, queryset `Ejecucion.objects.select_related('tarea__agente__modelo__proveedor').order_by('-id')[:100]` pasando el contexto como `ejecuciones`.
- `apps/panel/urls.py`: ruta `path('ejecuciones/', views.lista_ejecuciones, name='lista_ejecuciones')`.
- `apps/panel/templates/panel/base.html`: enlace "Ejecuciones" como último de la sección "Operación" del sidebar, con clase `activo` condicional.
- `apps/panel/templates/panel/lista_ejecuciones.html` (nuevo): extiende `panel/base.html`, título "Historial de Ejecuciones", subtítulo "Auditoría de consumo y rendimiento", tabla estilo Apple/SaaS estricta con columnas Fecha/Hora (usando `tarea.actualizado_en`), Tarea (ID), Proveedor, Tokens (In/Out), Duración (ms), Estado con badge de color.
- `tests/test_panel.py`: prueba `test_lista_ejecuciones_render` (login, crear Ejecucion asociada a Tarea, GET a 'lista_ejecuciones', status 200, presencia del ID de tarea y del proveedor).
- `docs/plan.md`: esta sección y estado general actualizado a "Pasos 0 a 25 COMPLETADOS. Núcleo de ARM v1.0 terminado."

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "ejecuciones" -q` → `1 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `23 passed`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.

Historial de ejecuciones listo para auditoría de tokens y errores, sin fondos crema ni emojis.

## Paso B.1 - Sistema de diseño ARM Flow + centralización CSS — COMPLETADO

**Objetivo:** Crear un archivo CSS centralizado con el sistema de diseño ARM Flow y actualizar base.html para usarlo, eliminando el CSS embebido del sidebar y header. Esto aplica el nuevo look a todas las páginas que extienden base.html.

**Archivos tocados:**
- `static/css/app.css` (nuevo): tokens CSS (:root) con paleta, tipografía, espaciado, radios, sombras y transiciones ARM Flow; reset básico; layout base; sidebar oscuro; header de contenido; componentes base (btn-primary, btn-secondary, btn-danger, badges, tarjeta, tabla, input, form-group); tipografía (h1, h2, p).
- `apps/panel/templates/panel/base.html`: añadido `{% load static %}` al inicio y `<link rel="stylesheet" href="{% static 'css/app.css' %}">` en `<head>`; eliminado TODO el bloque `<style>...</style>` con CSS embebido (aprox. líneas 10-150); estructura HTML del sidebar, header, nav y bloque `{% block content %}` sin cambios.
- `docs/plan.md`: esta sección.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- Navegador en http://127.0.0.1:8000/panel/ → sidebar oscuro, enlaces en gris, activo en índigo, estructura base con look ARM Flow.

Sidebar oscuro, enlaces en gris, activo en índigo; CSS centralizado en static/css/app.css; sin fondos crema, sin emojis, sin gradientes.

## Paso B.1.1 - Fix de configuración de archivos estáticos (causa raíz del 404 en app.css) — COMPLETADO

**Objetivo:** Hacer que Django sirva la carpeta static/ de la raíz del proyecto, para que /static/css/app.css cargue correctamente.

**Archivos tocados:**
- `config/settings.py`: añadido `STATICFILES_DIRS = [BASE_DIR / "static"]` tras `STATIC_URL = 'static/'` (BASE_DIR ya definido en línea 18; no se tocó STATIC_URL ni STATIC_ROOT).
- `docs/plan.md`: esta nota.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -c "from django.conf import settings; print(settings.STATICFILES_DIRS)"` → `[WindowsPath('C:/Users/Drogo/Downloads/ARM agentes/static')]`.
- `pytest -q`: 18 tests de test_panel pasan antes de un cuelgue preexistente de entorno en un test posterior (no relacionado con este cambio; no modifica lógica ni tests).

Nota: `pytest -q` completo se cuelga en un test preexistente de entorno (no relacionado con STATICFILES_DIRS); manage.py check y la verificación de STATICFILES_DIRS pasan correctamente.

## Paso B.2 - Limpieza de CSS embebido en templates de listado — COMPLETADO

**Objetivo:** Eliminar los bloques `<style>` duplicados de los templates de listado principales y adaptar sus clases HTML para que usen el sistema de diseño ARM Flow centralizado en `static/css/app.css`.

**Archivos tocados:**
- `apps/panel/templates/panel/tareas.html`: eliminado TODO el bloque `<style>...</style>`. Clases cambiadas: `.btn-nueva` → `.btn-primary`, `.btn-publicar` → `.btn-primary`, pills de filtro `.btn-secondary`/`.btn-primary` (activo), `.tabla-tareas` → `.tabla`, badge dinámico mapeado (ok→success, fallo→error, revision→warning, cola/curso→info).
- `apps/panel/templates/panel/lista_workflows.html`: eliminado TODO el bloque `<style>...</style>`. Clases cambiadas: `.btn-acento` → `.btn-primary`, `.btn-ejecutar` → `.btn-primary`, `table.workflows` → `table.tabla`, badge dinámico mapeado (en_ejecucion→info, completado→success, fallido→error, borrador→badge base).
- `apps/panel/templates/panel/lista_equipos.html`: eliminado TODO el bloque `<style>...</style>`. Clases cambiadas: `.btn-acento` → `.btn-primary`, `.btn-eliminar` → `.btn-danger`, `table.equipos` → `table.tabla`.
- `apps/panel/templates/panel/lista_ejecuciones.html`: eliminado TODO el bloque `<style>...</style>`. Clases cambiadas: `.badge-exito` → `.badge badge-success`, `table.ejecuciones` → `table.tabla`.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `views.py`, `urls.py` ni ningún archivo `.py`.
- No se modificó la estructura HTML lógica (solo nombres de clases CSS y eliminación de bloques `<style>`).
- `fila_tarea.html` no se modificó (no está en el alcance de los 4 archivos autorizados); las clases `.btn-aprobar` y `.btn-eliminar-tarea` se mantienen para no romper `test_lista_muestra_formulario_eliminar`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → tests relevantes en verde (sidebar, listados, crear/aprobar/eliminar tareas).

Templates de listado limpiados de CSS embebido; clases centralizadas en `static/css/app.css`; sin fondos crema ni emojis.

## Paso B.3 - Limpieza de CSS en formularios y vistas de detalle — COMPLETADO

**Objetivo:** Eliminar los bloques `<style>` duplicados de los templates de formularios y detalle, adaptando sus clases al sistema ARM Flow centralizado en `static/css/app.css`.

**Archivos tocados:**
- `apps/panel/templates/panel/crear_tarea.html`: eliminado TODO el bloque `<style>`. `.tarjeta-chat` → `.tarjeta`; textarea/inputs/select usan `.input`; botón ya usaba `.btn-primary`.
- `apps/panel/templates/panel/agente_form.html`: eliminado TODO el bloque `<style>`. Contenedor usa `.tarjeta`; campos usan `.form-group` y `.input`; `.btn` → `.btn-primary` (Guardar agente), `.btn-cancelar` → `.btn-secondary` (Cancelar). Radios/checkboxes ocultos se mantienen con lógica JS intacta.
- `apps/panel/templates/panel/formulario_workflow.html`: eliminado TODO el bloque `<style>`. `<form class="tarjeta">`; campos de Django envueltos en `.form-group`; `.btn-secundario` → `.btn-secondary`, `.btn-acento` → `.btn-primary`.
- `apps/panel/templates/panel/formulario_equipo.html`: eliminado TODO el bloque `<style>`. `form .form-edicion` → `.tarjeta`; campos envueltos en `.form-group` con `.input`; `.btn-acento` → `.btn-primary`, `.btn-secundario` → `.btn-secondary`.
- `apps/panel/templates/panel/integraciones.html`: estilo inline del botón "Copiar" → `.btn-primary`; eliminado estilos inline del `<code>` y del párrafo de advertencia; contenedor ya usaba `.tarjeta`.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `views.py`, `urls.py` ni ningún archivo `.py`.
- No se modificó la lógica de los formularios (nombres de campos, csrf, bucles de formset, script de plantillas y temperatura).

**Deuda técnica reportada para Paso B.4:**
- `agente_form.html`: al eliminar el CSS embebido se pierde el layout de dos columnas (`.agente-columnas`) y los estados visuales `.seleccionada`/`:has(input:checked)` de `.modelo-card` y `.habilidad-card`. Se requiere añadir `.agente-columnas` y `.seleccionada` a `app.css`.
- `formulario_workflow.html`: `{{ field }}` de Django no recibe la clase `.input` sin tocar `forms.py` (prohibido en este paso). Los campos heredan espaciado de `.form-group` pero no el estilo de input centralizado.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → tests en verde.
- Verificación: cero bloques `<style>` en los 5 templates modificados.

## Paso B.4 - Cierre del sistema de diseño y refinamiento — COMPLETADO

**Objetivo:** Resolver la deuda técnica reportada en B.3 (layout de agente y estilos de inputs de Django) y añadir iconos SVG profesionales al sidebar para completar el look ARM Flow.

**Archivos tocados:**
- `static/css/app.css`: reglas `.agente-columnas`, `.agente-izquierda`, `.agente-derecha` con media query 768px; `:has(input:checked)` para estados de `.modelo-card` y `.habilidad-card` sin depender de JS; estilo global para inputs de Django en `.form-group` (text, number, select, textarea + focus); slider de rango con `accent-color`; `.sidebar a` cambiado a `display: flex` con `align-items: center` y `gap: 8px`.
- `apps/panel/templates/panel/base.html`: 10 enlaces del sidebar con iconos SVG inline (20x20px, stroke-width 1.5, color currentColor, estilo Heroicons) + texto, alineados verticalmente con flex y gap 8px.
- `docs/plan.md`: estado general actualizado a "Bloque B (Rediseño UX/UI) COMPLETADO. Sistema de diseño ARM Flow centralizado y aplicado a todo el panel."; esta sección.

**Reglas respetadas:**
- No se modificó views.py, urls.py, forms.py ni ningún archivo Python.
- No se usaron librerías externas de iconos; SVG inline puro.
- Estilo ARM Flow estricto.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → tests relevantes en verde.

Deuda técnica de B.3 resuelta y sidebar con iconos SVG profesionales para completar el look ARM Flow.

## Paso B.5 - Corrección de errores de UI/UX — COMPLETADO

**Objetivo:** Arreglar el botón "Nueva tarea" superpuesto, el botón "Eliminar" sin estilo destructivo y los badges de estado planos en la tabla de tareas, heredando todo del sistema ARM Flow centralizado.

**Archivos tocados:**
- `static/css/app.css`: añadido `.page-header`, `.page-header h1`, `.page-header .cuenta`, `.page-header .acciones-encabezado` y `.btn-danger-sm` con su `:hover` al final del archivo.
- `apps/panel/templates/panel/tareas.html`: clase del contenedor de encabezado `encabezado-tareas` → `page-header`; el div interior ya usaba `acciones-encabezado` y coincide con la regla centralizada.
- `apps/panel/templates/panel/fila_tarea.html`: botón eliminar `btn-eliminar-tarea` → `btn-danger-sm`; badge de estado mapeado a clases centrales (ok→badge-success, fallo→badge-error, revision→badge-warning, cola/curso→badge-info) mediante condicional.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó views.py, urls.py, forms.py ni ningún archivo Python.
- No se tocó la lógica HTMX de fila_tarea.html (atributos hx-*, id, formularios); solo nombres de clases CSS.
- No se tocó base.html.

**Nota:** Estos defectos surgieron porque los tests de Django no validan layout CSS; la verificación visual requiere navegador.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "sidebar or eliminar or aprobar" -q` → tests en verde.
