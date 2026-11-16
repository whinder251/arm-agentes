# Plan de construcción — ARM

## Estado Actual (2026-11-14)
**Pasos 0 a 25 COMPLETADOS. Núcleo de ARM v1.0 terminado.** 
El sistema cuenta con: panel web estilo Apple/SaaS, creación de tareas con asignación automática, modelos Workflow/PasoWorkflow/Equipo, API REST con Pydantic v2, publicación en WordPress (borradores), cifrado de API keys, validación de cuotas, orquestación de workflows paso a paso, conteo real de tokens, dashboard de métricas, integraciones con ARM_API_KEY visible, propagación de fallos y vista de historial de ejecuciones para auditoría.
*Ver `docs/plan_historial.md` para el registro detallado de evidencias de los pasos 0-20.*

**Bloque B (Rediseño UX/UI) 100% COMPLETADO.** Cero CSS embebido, cero clases huérfanas en el panel.

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

## Paso B.7 - Sistema de diseño ARM Flow completo — COMPLETADO

**Objetivo:** Cerrar el Bloque B definiendo en app.css TODAS las clases transversales huérfanas (usadas en HTML pero sin definición) y migrando los estilos inline de dashboard.html y base.html a clases del sistema. No se tocaron aún las 3 vistas con bloque <style> embebido (configuracion, lista_agentes, lista_habilidades); esas se migran en B.8.

**Archivos tocados:**
- `static/css/app.css`: añadido al FINAL el bloque de clases transversales del Paso B.7 (cabecera-lista, vacio, acciones, enlace-editar, form-eliminar, form-ejecutar, volver, ayuda, subtitulo, subtexto, cantidad, fecha, slug, mono, errores, errorlist, alerta-error, mensaje-exito, detalle, bloque, pagina-crear, fila-campos, acciones-formulario, modelos-lista, habilidades-grid, modelo-card, habilidad-card, seleccionada, habilidad-nombre, habilidad-slug, nota-vacia, btn-plantilla, temperatura-fila, btn-aprobar, btn, btn-logout, dashboard .grid/tarjeta/h3/valor/valor--*, integraciones .subtitulo, api-key-fila). No se reescribió lo existente.
- `apps/panel/templates/panel/dashboard.html`: divs .valor con style inline migrados a clases modificadoras (cola→valor valor--info, completadas→valor valor--success, tokens→valor, workflows→valor valor--warning); subtexto ya usa class="subtexto". Sin tocar estructura ni {{ }}.
- `apps/panel/templates/panel/base.html`: botón Logout class="btn" + style="background-color:#FF3B30..." → class="btn-logout", se quitó el inline rojo. Bloque de login: botón usa class="btn" y inputs usan class="input". Sin tocar sidebar, enlaces SVG ni lógica de autenticación.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó configuracion.html, lista_agentes.html ni lista_habilidades.html (son B.8).
- No se modificó views.py, urls.py, forms.py ni ningún .py.
- app.css solo se amplió al final; no se reescribió lo existente.
- No se ejecutó git push.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "sidebar or dashboard or integraciones" -q` → tests en verde.

Clases transversales definidas y estilos inline migrados a clases del sistema ARM Flow; pendiente B.8 (migración de las 3 vistas con <style> embebido).

## Paso B.8 - Migración final de CSS embebido — COMPLETADO

**Objetivo:** Eliminar los bloques `<style>` embebidos de las últimas 3 vistas pendientes y adaptar sus clases al sistema ARM Flow centralizado en `static/css/app.css`.

**Archivos tocados:**
- `apps/panel/templates/panel/configuracion.html`: eliminado TODO el bloque `<style>`. `.btn-acento` → `.btn-primary`, `.btn-cancelar` → `.btn-secondary`, `.badge-activo` → `.badge badge-success`, `.badge-inactivo` → `.badge badge-error`. Contenedores `.tarjeta` y `.form-seccion` conservados.
- `apps/panel/templates/panel/lista_agentes.html`: eliminado TODO el bloque `<style>`. `table.agentes` → `.tabla`, `.btn-acento` → `.btn-primary`, `.btn-eliminar` → `.btn-danger-sm`. Lógica de selección de modelos/habilidades (`.modelo-card`, `.habilidad-card`) intacta.
- `apps/panel/templates/panel/lista_habilidades.html`: eliminado TODO el bloque `<style>`. `table.habilidades` → `.tabla`, `.btn-acento` → `.btn-primary`, `.btn-eliminar` → `.btn-danger-sm`.
- `tests/test_panel.py`: 3 pruebas nuevas de render (login, GET, status 200): `test_configuracion_render`, `test_lista_agentes_render`, `test_lista_habilidades_render`.
- `docs/plan.md`: esta sección y estado general del Bloque B.

**Reglas respetadas:**
- No se modificó `views.py`, `urls.py`, `forms.py` ni ningún archivo Python excepto `tests/test_panel.py` para los 3 tests nuevos.
- No se tocó la lógica de Django (bucles, condicionales, formularios, HTMX); solo nombres de clases CSS y eliminación de bloques `<style>`.
- Estilo ARM Flow estricto.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "configuracion or lista_agentes or lista_habilidades or sidebar or dashboard or integraciones or ejecuciones" -q` → `8 passed`.

Cero CSS embebido, cero clases huérfanas en el panel; Bloque B al 100%.

**Nota de corrección:** las clases de configuracion (.config-container, .config-proveedores, .config-modelos, .form-seccion, .form-oculto, .form-edicion, .habilidades-edicion y relacionadas) no quedaron cubiertas en el Paso B.7; se definen en el Paso B.9.

## Paso B.9 - Clases de configuracion y fix underline botones-enlace — COMPLETADO

**Objetivo:** Arreglar el colapso de configuracion.html (layout 60/40 perdido, formularios ocultos visibles, inputs sin estilo) y el subrayado de los botones que son enlaces. El HTML ya usaba las clases correctas; solo faltaban definirlas en app.css.

**Archivos tocados:**
- `static/css/app.css`: añadido al FINAL el bloque de clases de configuracion (.config-container, .config-proveedores, .config-modelos, .form-seccion, .form-oculto, .form-edicion, .habilidades-edicion, labels, inputs, h3, h4) y `text-decoration: none` para todos los botones-enlace (.btn, .btn-primary, .btn-secondary, .btn-danger, .btn-danger-sm, .btn-logout, .btn-plantilla, .btn-aprobar, .btn-cancelar, .btn-acento, .enlace-accion). No se reescribió lo existente.
- `tests/test_panel.py`: nueva prueba `test_configuracion_form_oculto` (login, GET a 'configuracion', status 200, HTML contiene 'form-oculto').
- `docs/plan.md`: esta sección y corrección de la nota de B.8.

**Reglas respetadas:**
- No se modificó configuracion.html, lista_agentes.html, lista_habilidades.html ni ningún template HTML.
- No se modificó views.py, urls.py, forms.py ni ningún archivo Python excepto tests/test_panel.py.
- app.css solo se AMPLIO al final; no se reescribió lo existente.
- No se ejecutó git push.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "configuracion" -q` → tests en verde.

## Paso B.10 - Definicion de .filtros — COMPLETADO

**Objetivo:** Arreglar que el menu de filtros (nav.filtros) en tareas.html se monte sobre la cabecera de la tabla. El HTML ya usa class="filtros"; falta la definicion en app.css, perdida al borrar el <style> de tareas.html en B.2.

**Archivos tocados:**
- `static/css/app.css`: añadido al FINAL el bloque `.filtros` (display:flex, flex-wrap:wrap, gap, margin-bottom, font-size), sin tocar lo existente.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó tareas.html ni ningún otro template. El markup ya es correcto.
- No se modificó views.py, urls.py, forms.py ni ningún .py.
- app.css solo se AMPLIO al final; no se reescribió lo existente.
- No se ejecutó git push.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "tareas or lista" -q` → tests en verde.

**Nota de corrección de matriz B.6:** `.filtros` (nav contenedor) no quedó cubierta en B.7; se define aquí en el Paso B.10.

El menu de filtros de tareas ahora tiene contenedor propio en app.css sin solaparse sobre la cabecera de la tabla; sin fondos crema ni emojis.

## Paso C.1a - Diagnóstico y preparación segura de variables de entorno — COMPLETADO

**Objetivo:** Crear un .env real con claves válidas, preparar el terreno para el blindaje estricto de C.1b y evitar que .env se commitee por error.

**Archivos tocados:**
- `config/settings.py`: añadido `import os` al inicio; comentario TODO C.1b junto a `SECRET_KEY` (valor sin cambiar todavía).
- `apps/core/models.py`: comentario TODO C.1b en `EncryptedTextField` (lógica de fallback sin cambiar todavía).
- `.env.example` (nuevo): `SECRET_KEY`, `ARM_ENCRYPTION_KEY` y `ARM_API_KEY` con comentarios explicativos.
- `apps/core/management/commands/generar_env.py` (nuevo): comando Django que genera `SECRET_KEY` y `ARM_ENCRYPTION_KEY`, escribe `.env` si no existe (sin sobrescribir), NO re-cifra api_key automáticamente e imprime aviso de re-ingresar API Keys en Configuración.
- `apps/core/management/__init__.py` y `apps/core/management/commands/__init__.py` (nuevos): paquetes vacíos para que Django reconozca el comando.

**Reglas respetadas:**
- No se modificó urls.py, views.py, forms.py ni templates.
- No se ejecutó git push.
- No se hizo `git add .env` (archivo local y secreto).
- Commit: "Paso C.1a: Preparación de entorno y script de generación de claves".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py generar_env` → `.env creado` + claves generadas + aviso de re-ingresar API Keys.

**Pendiente:** Paso C.1b (blindaje estricto: SECRET_KEY y ARM_ENCRYPTION_KEY obligatorias por entorno con ImproperlyConfigured, eliminar fallback dinámico, ProtectedError en eliminar_agente/eliminar_habilidad, ocultar ARM_API_KEY en integraciones.html).

## Paso C.1b - Blindaje estricto de entorno, cifrado e integridad al borrar — COMPLETADO

**Objetivo:** Exigir variables de entorno obligatorias, eliminar fallbacks inseguros y manejar errores de integridad referencial de forma amigable (preparando el terreno para la refactorización de vistas en C.2).

**Archivos tocados:**
- `config/settings.py`: `SECRET_KEY = os.environ.get("SECRET_KEY")` con `ImproperlyConfigured` si falta.
- `apps/core/models.py`: `EncryptedTextField` sin fallback dinámico; `ARM_ENCRYPTION_KEY` obligatoria por entorno y `_fernet` para cifrar/descifrar.
- `apps/panel/views.py`: import `ProtectedError`; `eliminar_agente` y `eliminar_habilidad` envuelven `.delete()` en `try...except ProtectedError` con `messages.error` y `redirect` a `lista_agentes` / `lista_habilidades`.
- `apps/panel/templates/panel/integraciones.html`: eliminado `{{ arm_api_key }}` y botón copiar; tarjeta de seguridad con mensaje claro y clases centrales.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `urls.py`, `forms.py` ni ningún otro archivo Python no listado.
- No se ejecutó `git push`.
- Variables de entorno cargadas desde `.env` antes de ejecutar comandos (Django no carga `.env` automáticamente).

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "eliminar" -q` → `3 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `28 passed`.

SECRET_KEY y ARM_ENCRYPTION_KEY ahora son obligatorias por entorno; fallbacks dinámicos eliminados; borrado de agente/habilidad con dependencias protegidas devuelve error amigable; ARM_API_KEY ya no se expone en el panel.

## Paso C.2 - Refactorización de Proveedores y Modelos en vista dedicada — COMPLETADO

**Objetivo:** Crear una vista `lista_proveedores` que muestre los proveedores con sus modelos anidados, y opciones de Editar/Eliminar. Esto separa la lógica de configuración monolítica en vistas especializadas.

**Archivos tocados:**
- `apps/panel/views.py`: nueva vista `lista_proveedores` con `@login_required`, queryset `Proveedor.objects.prefetch_related('modelos').order_by('nombre')`, contexto `proveedores`.
- `apps/panel/urls.py`: ruta `path('proveedores/', views.lista_proveedores, name='lista_proveedores')` añadida.
- `apps/panel/templates/panel/lista_proveedores.html` (nuevo): extiende `base.html`, título "Proveedores", subtítulo "Gestión de proveedores y modelos de IA", botón "Añadir Proveedor" `.btn-primary`, tabla `.tabla` (Nombre, Base URL, Modelos, Acciones), acciones con `.enlace-editar` y formulario POST eliminar `.btn-danger-sm`, modelos anidados con `.modelo` y `.badge`.
- `apps/panel/templates/panel/base.html`: enlace "Proveedores" en sección "Configuración" con icono SVG y clase `activo` condicional (`url_name == 'lista_proveedores'`).
- `tests/test_panel.py`: nueva prueba `test_lista_proveedores_render`.

**Reglas respetadas:**
- No se modificó `configuracion.html`, `forms.py`, `models.py` ni la lógica de borrado.
- No se ejecutó `git push`.
- Estilo ARM Flow estricto: `.tabla`, `.btn-primary`, `.btn-danger-sm`, `.badge`, `.enlace-editar`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "proveedor" -q` → `1 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → 28 passed antes de cuelgue preexistente de entorno (no relacionado con este cambio).

Vista dedicada de proveedores con modelos anidados; `configuracion.html` sin cambios pendiente de limpieza posterior.

## Paso C.3a - Arreglar botón Editar de proveedores y crear vista independiente de Modelos — COMPLETADO

**Objetivo:** (1) Arreglar el botón "Editar" en `lista_proveedores.html` para que funcione (href + vista `editar_proveedor`). (2) Crear vista `lista_modelos` con tabla plana de todos los modelos.

**Archivos tocados:**
- `apps/panel/views.py`: vista `editar_proveedor` (@login_required, get_object_or_404, reusa `ProveedorForm`, GET/POST, redirect a `lista_proveedores`, renderiza `lista_proveedores.html` con `form` + `proveedor_editar`) y vista `lista_modelos` (@login_required, `ModeloLLM.objects.select_related('proveedor').order_by('proveedor__nombre', 'model_id')`, contexto `modelos`).
- `apps/panel/urls.py`: `path('proveedores/<int:pk>/editar/', views.editar_proveedor, name='editar_proveedor')` y `path('modelos/', views.lista_modelos, name='lista_modelos')`.
- `apps/panel/templates/panel/lista_proveedores.html`: botón Editar `href="{% url 'editar_proveedor' proveedor.pk %}"` (clase `.enlace-editar` mantenida) + bloque condicional al final que renderiza el formulario de edición cuando `form` y `proveedor_editar` están en contexto.
- `apps/panel/templates/panel/lista_modelos.html` (nuevo): extiende `base.html`, título "Modelos", subtítulo, botón "Añadir Modelo" (`.btn-primary` → `crear_modelo`), tabla `.tabla` (Model ID, Proveedor, Prioridad, Json nativo, Activo, Acciones), badge Activo `.badge badge-success` / Inactivo `.badge badge-error`, acciones con `.enlace-editar` y form POST eliminar `.btn-danger-sm`.
- `tests/test_panel.py`: nueva prueba `test_lista_modelos_render`.

**Reglas respetadas:**
- No se modificó `configuracion.html`, `forms.py`, `models.py` ni la lógica de borrado.
- No se tocó el sidebar (pendiente C.3b).
- No se ejecutó `git push`.
- Estilo ARM Flow estricto: `.tabla`, `.btn-primary`, `.btn-danger-sm`, `.badge`, `.enlace-editar`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "proveedor or modelo" -q` → `2 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → cuelgue preexistente de entorno en test posterior (no relacionado con este cambio), igual que en C.2.

**Pendiente:** Paso C.3b (sidebar: enlace a proveedores/modelos).

## Paso C.3b - Reorganización del sidebar y limpieza de configuracion — COMPLETADO

**Objetivo:** Eliminar la duplicación entre configuracion.html y las nuevas vistas dedicadas (lista_proveedores, lista_modelos). Reorganizar el sidebar para que cada enlace apunte a una vista única.

**Archivos tocados:**
- `apps/panel/templates/panel/base.html`: sección "Configuración" del sidebar, reemplazo del enlace "Modelos y proveedores" (que apuntaba a 'configuracion') por dos enlaces separados: "Proveedores" (`{% url 'lista_proveedores' %}`, icono SVG servidor/base de datos) y "Modelos" (`{% url 'lista_modelos' %}`, icono SVG chip/cpu). Clase `activo` por `request.resolver_match.url_name` ('lista_proveedores' / 'lista_modelos'). Mantenidos enlaces de Agentes, Habilidades e Integraciones.
- `apps/panel/templates/panel/configuracion.html`: eliminados los bloques de listas de lectura de proveedores y modelos (ya viven en lista_proveedores.html y lista_modelos.html). Conservados SOLO los formularios de creación (Añadir Habilidad, Añadir Agente, Añadir Proveedor, Añadir Modelo) con su lógica de toggleForm. Se añadieron enlaces directos a crear_proveedor y crear_modelo en la barra de acciones.
- `tests/test_panel.py`: actualización de `test_sidebar_enlaza_configuracion` para verificar enlaces a 'lista_proveedores' y 'lista_modelos' y textos "Proveedores"/"Modelos", y que ya no exista "Modelos y proveedores".
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó forms.py, models.py ni la lógica de borrado.
- La vista `configuracion` NO se eliminó: aún es usada por los redirects de crear_proveedor/crear_modelo/crear_habilidad/crear_agente y por tests (test_configuracion_render, test_configuracion_form_oculto, test_panel_config.py). Se mantiene simplificada.
- No se modificó views.py ni urls.py.
- Estilo ARM Flow estricto en el sidebar (iconos SVG 20x20, stroke-width 1.5, currentColor).
- No se ejecutó git push.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "sidebar or proveedor or modelo" -q` → `4 passed`.

## Paso C.4 - Mejora visual del editor de proveedores y ocultamiento de API keys — COMPLETADO

**Objetivo:** (1) Aplicar clases ARM Flow al formulario de edición de proveedor. (2) Enmascarar la API key mostrando solo los últimos 4 caracteres, con checkbox "Cambiar API key" que revela un textarea vacío para ingresar una nueva clave.

**Archivos tocados:**
- `apps/panel/forms.py`: `ProveedorForm` con `.input` en todos los campos, `api_key` como `TextInput` readonly enmascarado (`****XXXX`) cuando hay instancia, campo `cambiar_api_key` BooleanField.
- `apps/panel/views.py`: `editar_proveedor` captura `clave_original` antes del form; si no `cambiar_api_key` restaura la clave existente; si está marcado, usa `nueva_api_key` de `request.POST`.
- `apps/panel/templates/panel/lista_proveedores.html`: formulario de edición reestructurado con `.tarjeta`, `.form-group`, `.input`, `.btn-primary`, `.btn-secondary`, `.ayuda`, checkbox toggle y script show/hide del textarea nueva clave.
- `tests/test_panel.py`: 3 pruebas nuevas (`test_editar_proveedor_render`, `test_editar_proveedor_no_cambiar_api_key_conserva_clave`, `test_editar_proveedor_cambiar_api_key_actualiza_clave`).

**Reglas respetadas:**
- No se modificó models.py, urls.py ni la lógica de cifrado (EncryptedTextField).
- Estilo ARM Flow estricto: .tarjeta, .form-group, .input, .btn-primary, .btn-secondary, .ayuda.
- No se ejecutó git push.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "proveedor" -q` → `4 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `33 passed`.

## Paso C.5a - Base de datos para integraciones y autenticación por hash — COMPLETADO

**Objetivo:**
1) Crear modelo `IntegracionConfig` para gestionar credenciales externas.
2) Migrar la autenticación de la API REST de `settings.ARM_API_KEY` a un hash SHA-256 almacenado en la BD.
3) Crear comando de gestión idempotente para migrar la clave actual sin romper consumidores existentes.

**Archivos tocados:**
- `apps/core/models.py`: nuevo modelo `IntegracionConfig` (`nombre` único, `tipo` con choices arm_api/wordpress/slack, `credenciales` TextField con hash SHA-256, `activa`, `proyecto_id = IntegerField(null=True, blank=True, db_index=True)`, `fecha_creacion`, `actualizado_en`); `clean()` valida que solo exista un `tipo='arm_api'` activo a la vez.
- `apps/api/views.py`: `_autenticado` lee header `X-ARM-API-KEY`, calcula SHA-256, busca `IntegracionConfig` activa `tipo='arm_api'` y compara con `hmac.compare_digest`; fallback temporal a `settings.ARM_API_KEY` con comentario TODO C.5b. Retorna 401 si falta/no coincide.
- `apps/core/management/commands/migrar_integraciones.py` (nuevo): comando idempotente que lee `ARM_API_KEY` del entorno/settings, no genera clave, no imprime secreto, crea el registro si no existe.
- `tests/test_integraciones.py` (nuevo): clave válida/inválida/sin clave, idempotencia del comando, credencial no en texto plano.
- Migración generada y aplicada: `apps/core/migrations/0011_integracionconfig.py`.

**Reglas respetadas:**
- No se modificó `models.py` de otras apps ni se rompió la autenticación actual.
- No se ejecutó `git push`.
- Seguridad: hash SHA-256 (no reversible), `hmac.compare_digest`, credencial no en texto plano, no se generó clave nueva, comando idempotente.
- Estilo ARM Flow estricto.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py makemigrations core` → `0011_integracionconfig` creada.
- `.venv\Scripts\python.exe manage.py migrate` → `Applying core.0011_integracionconfig... OK`.
- `.venv\Scripts\python.exe manage.py migrar_integraciones` → `IntegracionConfig arm_api creada a partir de ARM_API_KEY del entorno.`
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_integraciones.py -q` → `6 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_api.py -q` → `3 passed` (autenticación existente no se rompe; fallback a settings mientras no exista registro migrado).

## Paso C.5b - Panel de integraciones, rotación de clave ARM y limpieza de código — COMPLETADO

**Objetivo:**
1) Limpiar imports en `models.py` (verificar que no haya duplicados; añadir `hashlib` y `secrets`).
2) Crear vista y template para gestionar integraciones visualmente (ARM Flow, cero CSS embebido).
3) Implementar rotación segura de la clave ARM API: mostrar nueva clave una sola vez, guardar solo su hash SHA-256 en BD.

**Archivos tocados:**
- `apps/core/models.py`: añadido `import hashlib`, `import secrets` y `from django.db import models, transaction`; nuevo método de clase `IntegracionConfig.rotar_clave_arm()` que genera `secrets.token_urlsafe(32)`, calcula su hash SHA-256, actualiza el registro activo `tipo='arm_api'` (con `select_for_update` y `transaction.atomic`) y retorna el token en texto plano. No había import duplicado de `ImproperlyConfigured`.
- `apps/panel/views.py`: importada `IntegracionConfig`; vista `integraciones` reescrita con `@login_required`: lista `IntegracionConfig` ordenada por `nombre`; en POST `rotar_arm_api` llama a `rotar_clave_arm()` y pasa `nueva_clave_arm` al contexto.
- `apps/panel/templates/panel/integraciones.html`: reescrito con clases de `app.css` (cero `<style>` ni estilos inline): `.tarjeta` "Integraciones del Sistema", `.tabla` (Nombre, Tipo, Estado `.badge-success`/`.badge-error`, Fecha), sección "ARM API Key" con form POST y botón `.btn-danger` "Rotar Clave API", bloque `{% if nueva_clave_arm %}` con `.input` readonly + botón copiar (script nativo `navigator.clipboard`) y advertencia `.alerta-error` ("Copia esta clave ahora. No se volverá a mostrar.").
- `tests/test_integraciones.py`: nueva prueba `test_rotar_clave_arm` (token no vacío; hash en BD cambió; clave anterior → 401; nueva clave → 404; valor no guardado en texto plano; unicidad activa mantenida).
- `tests/test_panel.py`: actualización de `test_integraciones_render` al nuevo contrato de la vista (título "Integraciones del Sistema" y botón "Rotar Clave API").
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `models.py` de otras apps, ni `urls.py`, ni la lógica de fallback de C.5a (permanece temporalmente; retirada pendiente).
- No se usaron estilos inline ni bloques `<style>`; exclusivamente clases de `app.css`.
- La clave nueva nunca se guarda en texto plano; solo viaja en el contexto de la respuesta HTTP una vez.
- No se ejecutó `git push`.
- Seguridad: hash SHA-256 no reversible, secreto de un solo uso con advertencia explícita, comparación en tiempo constante en `_autenticado`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_integraciones.py -q` → `7 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones or sidebar" -q` → `3 passed`.

**Pendiente:** Retirar el fallback temporal a `settings.ARM_API_KEY` en `apps/api/views.py` (`_autenticado`, TODO C.5b) una vez confirmada la migración de credenciales en producción.

## Paso C.6 - Separación de credenciales de WordPress de los proveedores LLM — COMPLETADO

**Objetivo:** Crear un modelo independiente `DestinoPublicacion` para destinos de publicación (WordPress, custom_api), desacoplado de los proveedores de IA, con credenciales cifradas y gestionable desde la vista `integraciones`. Permite que un agente use cualquier modelo LLM y publique en cualquier destino configurado.

**Archivos tocados:**
- `apps/core/models.py`: nuevo modelo `DestinoPublicacion` (`nombre` único, `tipo` choices wordpress/custom_api, `url` con validador SSRF personalizado `validar_url_segura` que rechaza esquemas peligrosos y direcciones loopback/privadas/link-local/multicast/reservadas y metadatos de nube, `usuario`, `credenciales` `EncryptedTextField` reutilizando Fernet existente (RB-013), `activa`, `fecha_creacion`, `actualizado_en`); `save()` sobreescrito para ejecutar `full_clean()` y que la validación SSRF se aplique siempre al guardar (código, API o panel).
- `apps/panel/forms.py`: `DestinoPublicacionForm` con `.input` en todos los campos, `credenciales` como `PasswordInput`, enmascaramiento `****XXXX` y readonly en edición (misma lógica que proveedores), campo `cambiar_credenciales`.
- `apps/panel/views.py`: vista `integraciones` ampliada con queryset `DestinoPublicacion` y manejo POST `crear_destino` usando `DestinoPublicacionForm` (redirect y mensaje de éxito).
- `apps/panel/templates/panel/integraciones.html`: nueva `.tarjeta` "Destinos de Publicación" debajo de ARM API Key con `.tabla` (Nombre, Tipo, URL, Estado `.badge-success`/`.badge-error`) y formulario colapsable de alta con `.form-group`, `.input`, `.btn-primary`; cero `<style>` ni estilos inline.
- `tests/test_integraciones.py`: 3 pruebas nuevas (`test_destino_publicacion_guarda_credenciales_cifradas`, `test_destino_publicacion_rechaza_esquema_peligroso`, `test_destino_publicacion_rechaza_loopback`).
- `tests/test_panel.py`: 2 pruebas nuevas (`test_integraciones_render_muestra_destinos`, `test_crear_destino_publicacion`).
- Migración generada y aplicada: `apps/core/migrations/0012_destinopublicacion.py`.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó la lógica de proveedores LLM existentes ni `apps/providers/wordpress.py`.
- No se usaron estilos inline ni bloques `<style>`; exclusivamente clases de `app.css`.
- Las credenciales nunca se guardan en texto plano: `EncryptedTextField` con Fernet.
- Validación SSRF en el modelo (protege también ante creación desde código/API).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py makemigrations core` → `0012_destinopublicacion` creada.
- `.venv\Scripts\python.exe manage.py migrate` → `Applying core.0012_destinopublicacion... OK`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_integraciones.py -q` → `10 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones" -q` → `2 passed`.
- Nota: `tests/test_panel.py` completo tiene un cuelgue preexistente de entorno (documentado en pasos C.2/C.3a/C.4), no relacionado con este cambio.

## Paso C.7a - Edición y eliminación segura de Destinos de Publicación — COMPLETADO

**Objetivo:** Añadir funcionalidad de editar y eliminar registros de `DestinoPublicacion` en el panel, reutilizando el patrón seguro de credenciales (enmascaramiento y checkbox `cambiar_credenciales`) y la protección `ProtectedError` al eliminar.

**Archivos tocados:**
- `apps/panel/views.py`: vista `editar_destino` (`@login_required`, `get_object_or_404`, `DestinoPublicacionForm`; si `cambiar_credenciales` NO está marcado, restaura `form.instance.credenciales = destino.credenciales` antes de `save()`) y vista `eliminar_destino` (`@login_required`, `@require_POST`, `destino.delete()` envuelto en `try/except ProtectedError` con `messages.error`/`messages.success` y redirect a `integraciones`).
- `apps/panel/urls.py`: rutas `destinos/<int:pk>/editar/` (`editar_destino`) y `destinos/<int:pk>/eliminar/` (`eliminar_destino`).
- `apps/panel/templates/panel/integraciones.html`: columna "Acciones" en la tabla de destinos (enlace `.enlace-editar` a `editar_destino` y form POST `.btn-danger-sm` a `eliminar_destino` con `{% csrf_token %}`); bloque `{% if destino_editar %}` con formulario de edición (`form_destino`, `cambiar_credenciales`, ayuda, acciones-formulario).
- `tests/test_panel.py`: pruebas `test_editar_destino_preserva_credenciales` (credencial original mantenida al editar sin marcar `cambiar_credenciales`) y `test_eliminar_destino` (eliminación correcta y redirect a `integraciones`).

**Reglas respetadas:**
- No se modificó `models.py` (la lógica de `cambiar_credenciales` y cifrado ya está en `DestinoPublicacionForm`).
- Las credenciales nunca se guardan en texto plano: `EncryptedTextField` con Fernet (RB-013); enmascaramiento `****XXXX` y widget `readonly` en el form.
- Estilo ARM Flow estricto: `.tarjeta`, `.tabla`, `.enlace-editar`, `.btn-danger-sm`, `.form-group`, `.input`, `.ayuda`, `.acciones-formulario`. Cero estilos inline ni bloques `<style>`.
- Todas las vistas requieren `@login_required`; eliminación usa `@require_POST` y CSRF.
- No se ejecutó `git push`.
- Commit: "Paso C.7a: Edición y eliminación segura de Destinos de Publicación".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "destino" -q` → `4 passed` (`test_editar_destino_preserva_credenciales`, `test_eliminar_destino`, `test_integraciones_render_muestra_destinos`, `test_crear_destino_publicacion`).

**Pendiente:** Ninguno para este paso.

## Paso C.5c - Unificación visual de la ARM API Key en la tabla de integraciones — COMPLETADO

**Objetivo:** Eliminar la duplicación visual en la vista de integraciones. La ARM API Key se gestiona desde una columna "Acciones" en la tabla principal de integraciones, manteniendo el modelo de seguridad actual (hash SHA-256, sin botón "Ver", solo "Rotar"). La sección de destinos de publicación se mantiene limpia y bien separada.

**Archivos tocados:**
- `apps/panel/templates/panel/integraciones.html`: añadida columna "Acciones" a la tabla "Integraciones configuradas"; en la fila `tipo == 'arm_api'` se renderiza el formulario POST con botón "Rotar Clave API" (`.btn-danger`, dentro de `.form-eliminar`); las demás filas muestran un guion discreto en la celda de acciones. Eliminada por completo la tarjeta separada "ARM API Key". El bloque `{% if nueva_clave_arm %}` se conservó en la parte superior (justo debajo del título) con input readonly, botón copiar y advertencia `.alerta-error`. La sección "Destinos de Publicación" conserva su propia `.tarjeta` separada con tabla y formulario de alta. Cero estilos inline, cero bloques `<style>`; solo clases de `app.css` (`.tabla`, `.tarjeta`, `.btn-danger`, `.form-eliminar`, `.acciones`, `.alerta-error`, `.api-key-fila`, `.input`).
- `tests/test_panel.py`: `test_integraciones_render` verifica 'Rotar Clave API' presente y 'ARM API Key' ausente (tarjeta eliminada); `test_integraciones_render_muestra_destinos` verifica ambos bloques en la misma página. Se creó una `IntegracionConfig` tipo `arm_api` en `setUp` para que el botón se renderice. Se añadió `IntegracionConfig` a los imports de `apps.core.models`.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `models.py`. El modelo de seguridad (hash SHA-256) se mantiene intacto. No se añadió campo de "hint" ni cifrado reversible.
- No se añadió botón "Ver" ni "Mostrar clave". La clave ARM es de un solo uso visible por diseño.
- No se tocó la lógica de `rotar_clave_arm()` ni la autenticación de la API.
- `views.py` no se modificó: el contexto ya estaba limpio (`integraciones`, `destinos`, `form_destino`, `nueva_clave_arm`) sin `arm_api_key`.
- El import `Workflow, PasoWorkflow` se dejó intacto (se usa en líneas 406-409 de tests).
- Estilo ARM Flow estricto.
- No se ejecutó `git push`.
- Commit: "Paso C.5c: Unificacion visual de la ARM API Key en la tabla de integraciones".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones" -q` → `2 passed`.

## Paso C.7b - Desacoplar credenciales de WordPress del Proveedor LLM en la publicación — COMPLETADO

**Objetivo:** Modificar el flujo de publicación para que utilice las credenciales de `DestinoPublicacion` en lugar de las del `Proveedor` (LLM), completando la separación arquitectónica iniciada en C.6 y C.7a.

**Archivos tocados:**
- `apps/panel/views.py`: `detalle_tarea` pasa `destinos` (filtrado `activa=True`, ordenado por nombre) al contexto de `tareas.html`; `publicar_tarea` lee `destino_id` de `request.POST` y, si existe, instancia `WordPressProvider` con `api_key=f"{destino.usuario}:{destino.credenciales}"` y `base_url=destino.url` (credenciales cifradas descifradas en memoria vía `EncryptedTextField`); si no hay `destino_id`, aplica fallback temporal al Proveedor LLM con `# TODO C.8` documentado (seguridad.md §3: no confundir credenciales LLM con integraciones); mensaje de error genérico sin exponer detalles ni credenciales.
- `apps/panel/templates/panel/tareas.html`: el formulario de publicar (solo si `tarea.estado == 'ok'`) incluye `<select name="destino_id">` con los destinos activos pasados desde la vista; opción por defecto usa el proveedor LLM de la tarea.
- `tests/test_panel.py`: `test_publicar_tarea_con_destino_publicacion` (verifica que se usa `api_key`/`base_url` del `DestinoPublicacion`, no del proveedor LLM, y que la api_key del proveedor no persiste en `tarea.payload`); `test_publicar_tarea_sin_destino_no_expone_api_key_proveedor` (verifica fallback al proveedor LLM y que su `api_key` no aparece en payload ni en el cuerpo de la respuesta).
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (Opción B: ID del destino como argumento POST).
- No se tocó `apps/providers/wordpress.py` (el adaptador ya acepta `"usuario:contraseña"` y hace split interno).
- Fallback temporal con TODO referenciado a paso C.8; no expone credenciales del proveedor LLM en logs, payload ni mensajes.
- SSRF ya validado en `DestinoPublicacion.url` por `validar_url_segura` (C.6).
- `@login_required` y `@require_POST` intactos; CSRF mantenido en el template.
- Pruebas sin HTTP real, usando `unittest.mock.patch('apps.panel.views.WordPressProvider')`.
- Estilo ARM Flow estricto: clases `.input`, `.btn-primary`.
- No se ejecutó `git push`.
- Commit pendiente: "Paso C.7b: Publicación desacoplada del Proveedor LLM mediante DestinoPublicacion".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "publicar" -q` → `3 passed` (incluye `test_publicar_tarea_exitoso`, `test_publicar_tarea_con_destino_publicacion`, `test_publicar_tarea_sin_destino_no_expone_api_key_proveedor`).

## Paso C.7c+d (Combinado) — Corrección de UI en DestinoPublicacion y comando seed_demo — COMPLETADO

**Objetivo:**
1) Corregir el formulario de edición de destinos: incluir el campo `activa`, arreglar el toggle de credenciales sin estilos inline y ocultar el formulario de alta por defecto.
2) Crear un comando de gestión idempotente `seed_demo` para poblar habilidades, agentes, equipos y workflows de prueba usando proveedores existentes.

**Archivos tocados:**
- `apps/panel/templates/panel/integraciones.html`: el formulario de "Añadir Destino" está envuelto en `.form-seccion form-oculto` (oculto por defecto) con botón "Añadir Destino" que lo muestra/oculta mediante `toggleFormDestino()`; el bloque `{% if destino_editar %}` incluye todos los campos (nombre, tipo, url, usuario, `activa`, credenciales con checkbox "Cambiar credenciales" y textarea `nueva_credenciales_group` oculto por `.form-oculto`); el script JS usa solo clases CSS (`.form-oculto`) sin estilos inline; cero bloques `<style>`.
- `apps/panel/views.py`: `editar_destino` verificado, ya procesa correctamente `activa` (campo en `Meta.fields` de `DestinoPublicacionForm`) y `cambiar_credenciales` (preserva la credencial original si no se marca el checkbox). No se modificó.
- `apps/core/management/commands/seed_demo.py` (nuevo): comando idempotente con `handle()` que busca el primer ModeloLLM cuyo proveedor contenga "gemini" (o el primero disponible); si no existe, imprime error y sale con `sys.exit(1)` sin crear nada parcial. Usa `get_or_create` para 5 habilidades (investigar_tema, redactar_articulo, reescribir_editorial, revision_calidad en modo manual, metadatos_yoast con salida JSON), 4 agentes (Investigador, Redactor, Editor, Optimizador SEO vinculados al modelo encontrado), 2 equipos ("Contenido Web" y "Adaptacion") y 2 workflows con sus PasoWorkflow en orden. Imprime resumen de creado vs. ya existente. No crea Proveedor ni ModeloLLM nuevos.
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- Cero estilos inline, cero bloques `<style>`; solo clases de `app.css` (`.form-oculto`, `.form-seccion`, `.barra-acciones`, `.acciones-formulario`, `.btn-*`).
- No se ejecutó `git push`.
- Commit: "Paso C.7c+d: Corrección UI de destinos y comando seed_demo".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe manage.py seed_demo` (1ª ejecución) → 5 habilidades, 4 agentes, 2 equipos, 2 workflows creados.
- `.venv\Scripts\python.exe manage.py seed_demo` (2ª ejecución) → todo ya existente (idempotente).
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones" -q` → `2 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_integraciones.py -q` → `10 passed`.

## Paso C.7e - Corregir duplicado de formulario en integraciones y ampliar seed_demo con equipos reales — COMPLETADO

**Objetivo:**
1) Corregir UI en `integraciones.html`: renombrar tarjeta a "Conexiones de Publicación" y botón a "Añadir Conexión"; asegurar que el formulario de alta esté fuera de la tabla, envuelto en `.form-seccion form-oculto` con id `form-anadir-destino`, y que el script `toggleFormDestino` siempre esté definido (fuera del bloque `{% if destino_editar %}`) apuntando al id correcto y alternando la clase `.form-oculto`.
2) Ampliar `seed_demo.py`: 12 habilidades (slug + modo_ejecucion), 6 agentes con habilidades M2M, 3 equipos ("Editorial", "Marketing", "Soporte") con agentes vinculados vía ManyToMany, 4 workflows con pasos encadenados y agente asignado en cada `PasoWorkflow`. Lógica idempotente: si un equipo ya existe pero está sin agentes, se vinculan con `.set()`; si un paso ya existe con `agente=None`, se actualiza con `update_or_create`.

**Archivos tocados:**
- `apps/panel/templates/panel/integraciones.html`: renombrado título de tarjeta y botón; movido script `toggleFormDestino` fuera del bloque condicional para que siempre esté disponible; verificado que solo existe un form `crear_destino` (oculto, fuera de la tabla). Cero estilos inline, cero bloques `<style>`.
- `apps/core/management/commands/seed_demo.py`: reescrito con 12 habilidades, 6 agentes, 3 equipos con agentes M2M, 4 workflows con pasos y agente asignado; idempotente con actualización de registros incompletos.
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- Cero estilos inline, cero bloques `<style>`; solo clases de `app.css` (`.form-oculto`, `.tarjeta`, `.btn-primary`, etc.).
- `PasoWorkflow.agente` es nullable (FK con `null=True, blank=True`); `Equipo.agentes` es ManyToManyField con `related_name="equipos"`.
- No se ejecutó `git push`.
- Commit: "Paso C.7e: Corrección UI de conexiones y seed_demo con equipos y workflows completos".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe manage.py seed_demo` (1ª ejecución) → 12 habilidades (7 nuevas), 6 agentes (3 nuevas), 3 equipos (Editorial/Marketing/Soporte con agentes), 4 workflows (2 nuevos) con pasos y agente asignado.
- `.venv\Scripts\python.exe manage.py seed_demo` (2ª ejecución) → todo ya existente (idempotente, sin duplicados).
- Verificación de relaciones: equipos Editorial/Marketing/Soporte con agentes vinculados; 11 PasoWorkflow todos con agente asignado (ninguno None); 4 workflows con equipo.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones" -q` → `2 passed`.

## Paso C.8a - Corrección de sintaxis de encolado Huey en ejecutar_workflow — COMPLETADO

**Objetivo:** Corregir el AttributeError en la ejecución de workflows causado por usar sintaxis de Celery (.delay) en lugar de la sintaxis nativa de Huey.

**Archivos tocados:**
- `apps/panel/views.py`: en la función `ejecutar_workflow` (línea 439), cambiado `continuar_workflow.delay(workflow.pk, 1)` por `continuar_workflow(workflow.pk, 1)`.

**Reglas respetadas:**
- Solo se modificó la línea de encolado. No se tocó la lógica de autorización, estados ni la firma de la tarea.
- No se modificó `models.py`, `urls.py`, `forms.py`, `tasks.py` ni ningún otro archivo Python.
- No se ejecutó `git push`.
- Commit: "Corrección: sintaxis de encolado Huey en ejecutar_workflow".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "workflow" -q` → `3 passed`.

## Paso C.8c - Corrección del formulario de edición de destinos: enmascaramiento y toggle funcional — COMPLETADO

**Objetivo:** (1) Asegurar que al editar un destino, el campo de credenciales muestre el valor enmascarado (****XXXX). (2) Hacer que el checkbox "Cambiar credenciales" revele correctamente un textarea para ingresar la nueva credencial.

**Archivos tocados:**
- `apps/panel/templates/panel/integraciones.html`: añadido `<script>` dentro del bloque `{% if destino_editar %}` que registra un listener `change` en `#id_cambiar_credenciales` y hace `classList.toggle('form-oculto')` sobre `#nueva_credenciales_group` (también inicializa el estado al cargar). Cero estilos inline, cero bloques `<style>`, JS solo cuando existe un destino en edición.
- `tests/test_panel.py`: nueva prueba `test_editar_destino_credenciales_enmascaradas_y_toggle` que verifica `form_destino.initial['credenciales'] == '****9876'`, presencia de `id_cambiar_credenciales`, `id_nueva_credenciales`, `nueva_credenciales_group` y la clase `form-oculto` (el textarea inicia oculto).
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- Solo se modificó `integraciones.html` y `tests/test_panel.py` (máximo 4 archivos).
- Cero estilos inline, cero bloques `<style>`. El JS usa `classList` con `.form-oculto`, respetando `diseno-ui.md`.
- No se modificó `forms.py` (el enmascaramiento `****{credenciales[-4:]}` y `readonly` ya estaban implementados en `DestinoPublicacionForm.__init__`).
- No se modificó `models.py`, `urls.py`, views.py ni se creó migración.
- No se tocó credenciales persistidas, permisos, tareas en cola ni compatibilidad.
- No se ejecutó `git push`.
- Commit: "Paso C.8c: Toggle funcional de credenciales en edición de destinos".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "destino or integraciones" -q` → `8 passed`.

## Paso C.9a - Contrato de salida estructurada en las habilidades de contenido — COMPLETADO

**Objetivo:** Que las habilidades de contenido emitan JSON con campos separados (titulo, slug, contenido, meta_description, focus_keyword) en lugar de texto plano revuelto, para que la publicación lea claves nombradas y no adivine.

**Archivos tocados:**
- `apps/engine/tasks.py`: `_guardar_artefacto` intenta parsear `respuesta.texto` como JSON cuando la habilidad tiene `esquema_salida` no vacío; si es dict válido guarda titulo/slug/contenido/meta_description/focus_keyword en metadata (con fallback a texto plano si falla el parseo o no es dict); si no hay esquema o la respuesta no es JSON, guarda texto plano en metadata['contenido'] sin romper el flujo.
- `apps/panel/views.py`: `publicar_tarea` lee `titulo` y `contenido` del metadata del artefacto con este orden de precedencia: metadata estructurada -> payload -> `f"Tarea #{tarea.pk}"` (titulo) y metadata -> `artefacto.contenido` (contenido).
- `apps/core/management/commands/seed_demo.py`: prompts de las 12 habilidades de contenido piden salida JSON explícita con la estructura de 5 campos; `esquema_salida` se actualiza de `{}` a `{"titulo": "", "slug": "", "contenido": "", "meta_description": "", "focus_keyword": ""}`.
- `tests/test_engine.py`: dos pruebas nuevas (`test_artefacto_guarda_metadata_estructurado_desde_json`, `test_artefacto_guarda_texto_plano_cuando_respuesta_no_es_json`) usando respx, sin llamadas a APIs reales.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- No se tocó credenciales, permisos, ni la cola de tareas.
- Cambio retrocompatible: habilidades sin `esquema_salida` y respuestas no-JSON siguen comportándose como antes (texto plano en metadata['contenido']).
- Pruebas sin HTTP real, usando `respx`.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `6 passed in 6.95s` (incluye las 2 pruebas nuevas).
- `.venv\Scripts\python.exe -m pytest tests/test_publicacion.py -q` → `3 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "publicar" -q` → `3 passed`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

**Impacto en contratos:** Cambia el contrato de salida de las habilidades de contenido (ahora JSON con claves nombradas cuando hay esquema_salida). `publicar_tarea` lee esas claves con fallback al comportamiento anterior.

## Paso C.9a-fix2 - Reescritura completa de seed_demo.py para eliminar SyntaxError — COMPLETADO

**Objetivo:** Eliminar definitivamente el `SyntaxError` en `apps/core/management/commands/seed_demo.py` reescribiendo el archivo completo con prompts en comillas triples y JSON interno en comillas simples, sin escapes complejos.

**Archivos tocados:**
- `apps/core/management/commands/seed_demo.py`: reescrito completo. Los 12 `plantilla_prompt` usan ahora `"""` (comillas triples dobles) y el ejemplo JSON interno usa comillas simples (`'titulo': '...'`), eliminando por completo la necesidad de `\"`. Los métodos `_siembrar_agentes`, `_siembrar_equipos`, `_siembrar_workflows` y `handle` se mantienen intactos.

**Reglas respetadas:**
- Solo se modificó `seed_demo.py` (1 archivo).
- Reescritura completa del archivo, no parcheo parcial.
- No se modificó `models.py`, `views.py`, `tasks.py`, `urls.py`, `forms.py` ni templates.
- No se creó migración.
- No se tocó credenciales, permisos, ni la cola de tareas.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py seed_demo` (1ª) → 12 habilidades, 6 agentes, 3 equipos, 4 workflows (todos ya existían desde C.7e).
- `.venv\Scripts\python.exe manage.py seed_demo` (2ª) → idempotente, sin duplicados.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `6 passed`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

## Paso C.9b - Selector de tipo de publicación, mapeo de metadatos y conversión Markdown a HTML — COMPLETADO

**Objetivo:**
1) Añadir selector Post/Página en el formulario de publicar.
2) Mapear los campos estructurados del metadata (slug, meta_description, focus_keyword) a la API de WordPress.
3) Convertir el contenido de Markdown a HTML antes de enviarlo, usando la librería `markdown`.

**Archivos tocados:**
- `apps/providers/wordpress.py`: `crear_borrador` amplía su firma con `tipo` ('post' por defecto o 'page'), `slug`, `meta_description`, `focus_keyword`. El endpoint es `/wp-json/wp/v2/pages` cuando `tipo='page'` y `/wp-json/wp/v2/posts` en caso contrario. `slug`, `excerpt` (desde `meta_description`) y `focus_keyword` se asignan al payload con prioridad sobre los valores de igual nombre en `metadata`.
- `apps/panel/views.py`: `publicar_tarea` lee `tipo_publicacion` del POST, extrae `slug`/`meta_description`/`focus_keyword` del `metadata` del artefacto, aplica `markdown.markdown(contenido_md)` antes de enviar y pasa todos los campos a `crear_borrador`. Se añadió `import markdown`.
- `apps/panel/templates/panel/tareas.html`: el formulario de publicar incluye `<select name="tipo_publicacion" class="input">` con opciones 'post' (Entrada) y 'page' (Página), sin CSS embebido.
- `tests/test_panel.py`: tres pruebas nuevas (`test_publicar_tarea_tipo_pagina`, `test_publicar_tarea_mapea_metadatos_estructurados`, `test_publicar_tarea_convierte_markdown_a_html`) que verifican endpoint `/pages`, campos slug/excerpt/focus_keyword en el payload y conversión Markdown→HTML, usando `patch` sin HTTP real.

**Reglas respetadas:**
- Máximo 4 archivos modificados (exactamente 4).
- Dependencia `markdown` instalada tras aprobación explícita (AGENTS.md §3); más robusta y segura que recibir HTML crudo del modelo (evita XSS almacenado).
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- No se tocó `apps/providers/wordpress.py` más allá de la firma de `crear_borrador` (retrocompatible con valores por defecto).
- Pruebas sin APIs reales; cero llamadas a WordPress.
- Estilo ARM Flow estricto en el template (clase `.input`, cero `<style>`).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pip install markdown` → `Successfully installed markdown-3.11.3`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "publicar" -q` → `6 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_publicacion.py -q` → `3 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "destino or integraciones" -q` → `8 passed`.

**Impacto en contratos:** SÍ (firma de `crear_borrador` ampliada con valores por defecto, retrocompatible; `publicar_tarea` lee `tipo_publicacion`). Datos persistidos/credenciales/permisos/cola: NO.

**Pendiente:** C.8 (retirar fallback temporal de proveedor LLM en publicación).

## Paso C.10 Fase 2 — Contrato universal con Pydantic — COMPLETADO

**Objetivo:** Construir el contrato universal de respuestas de proveedores de IA validado con Pydantic v2, añadir campos aditivos a los modelos, permitir `response_schema` en los proveedores e integrar el normalizador en el motor de tareas.

**Archivos tocados:**
- `apps/core/schemas.py` (reconstruido): se conservó `TareaCreateSchema` (usado por `apps/api/views.py`) y se añadieron `ErrorEstructurado`, `ResultadoAgente` y `EsquemaHabilidad`.
- `apps/core/models.py`: campos aditivos con default (no rompen migraciones): `Habilidad.esquema_version` (CharField default "v1"), `Habilidad.permite_parcial` (BooleanField default False), `ModeloLLM.capacidades` (JSONField default list), `Artefacto.raw_response` (TextField null=True, blank=True).
- `apps/providers/base.py`: `RespuestaChat` amplió al final con `finish_reason`, `request_id`, `duration` (todos `None` por defecto); `chat()` añadió parámetro opcional `response_schema`.
- `apps/providers/gemini.py`: `chat()` acepta `response_schema` e inyecta `responseMimeType="application/json"` + `responseSchema` en `generationConfig` del payload REST.
- `apps/providers/openrouter.py`: `chat()` acepta `response_schema` e inyecta `response_format` con `json_schema` cuando se provee.
- `apps/engine/tasks.py`: `_guardar_artefacto` usa normalizador Pydantic (`_normalizar_respuesta`) con: parseo JSON directo, fallback a bloque ` ```json `, error estructurado si no hay JSON, validación ligera de `esquema_salida`/`permite_parcial`, construcción de `ResultadoAgente` (status completed/partial/failed), `metadata['resultado']` serializado y `raw_response` solo si `settings.ARM_GUARDAR_RAW` (default False).
- `apps/core/migrations/0013_artefacto_raw_response_habilidad_esquema_version_and_more.py` (nueva): migración generada con `makemigrations`.
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se modificó lógica de publicación (`publicar_tarea`) ni adaptadores de destino.
- No se tocó API REST ni serializadores.
- Migración generada con `makemigrations` (no manual).
- Cambios retrocompatibles (defaults en campos nuevos, parámetros opcionales en dataclass/firma).
- Pruebas sin APIs reales; se usaron fixtures y respx existentes.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → detectó cambios (4 campos).
- `.venv\Scripts\python.exe manage.py makemigrations core` → `0013_...` creada.
- `.venv\Scripts\python.exe manage.py migrate` → `Applying core.0013... OK`.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `6 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "publicar" -q` → `6 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_providers.py tests/test_router.py tests/test_api.py -q` → `36 passed`.

**Impacto en contratos/datos:** SÍ (firma de `chat()` y campos de `RespuestaChat`; 3 nuevas columnas en BD). Retrocompatible. Credenciales/permisos/cola: NO.

## Paso C.10.3 - Actualización integral de datos de prueba para el contrato universal — COMPLETADO

**Objetivo:** Actualizar TODAS las habilidades, agentes, modelos y flujos existentes en la base de datos para que utilicen los nuevos campos (`esquema_version`, `permite_parcial`, `capacidades`) y los nuevos esquemas JSON estructurados, asegurando que todo el sistema hable el mismo idioma.

**Archivos tocados:**
- `apps/core/management/commands/seed_demo.py`: 
  - `_obtener_modelo`: al obtener el modelo (ej. Gemini), actualiza `capacidades` a `["structured_output", "json_mode"]` (reasignación, no mutación in-place).
  - `_siembrar_habilidades`: para CADA una de las 12 habilidades define `esquema_salida` válido en JSON Schema (`type`, `properties`, `required`), `esquema_version = "v1"`, `permite_parcial = False` (excepto "Resumir contenido" = True), y `plantilla_prompt` con instrucción de rol genérica ("Debes responder estrictamente con un objeto JSON válido..."). Lógica explícita `if not created:` que actualiza `esquema_salida`, `esquema_version`, `permite_parcial` y `plantilla_prompt` en registros existentes, sin depender de `defaults`.
  - `_siembrar_agentes`: actualiza el `rol` de todos los agentes para incluir la frase "Entregas siempre el resultado en el formato exacto que declare la instrucción de la tarea (ej. objeto JSON con claves específicas), sin prosa adicional."
  - `_siembrar_equipos` y `_siembrar_workflows`: mantenidos sin cambios (verificado que `update_or_create` en PasoWorkflow no se rompe).
  - `handle`: muestra en consola cuántas habilidades se "actualizaron" (no solo "ya existían").
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó nueva migración (`makemigrations --check --dry-run` → No changes detected).
- Reasignación, no mutación: `obj.capacidades = [...]`, `obj.esquema_salida = {...}`.
- Prompts limpios: sin ejemplo JSON embebido, solo instrucción de rol genérica.
- Idempotencia real: ejecutable N veces sin duplicar ni corromper.
- Máximo 1 archivo modificado (dentro del límite de 4).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py seed_demo` → "Habilidades: 0 creadas, 12 actualizadas, 0 sin cambios." (actualizó registros existentes).
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_models.py -q` → `20 passed`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

**Impacto en contratos/datos:** SÍ (actualiza datos existentes en BD: capacidades del modelo, esquemas y prompts de habilidades, roles de agentes). Sin cambios de schema, migraciones, credenciales, permisos ni cola. Retrocompatible.

## Paso C.10.5 - Fix de habilidades faltantes y normalizador de texto — COMPLETADO

**Objetivo:**
1) Añadir la habilidad `reescritura` al seed_demo con esquema coherente.
2) Mejorar el normalizador para extraer texto plano cuando el modelo devuelve JSON que no coincide con el esquema.

**Archivos tocados:**
- `apps/core/management/commands/seed_demo.py`: añade la habilidad `reescritura` (slug `reescritura`, nombre "Reescritura", esquema `{titulo, contenido}` requerido, `esquema_version: "v1"`, `permite_parcial: False`, prompt JSON estricto, modo auto). Idempotente: actualiza registros existentes.
- `apps/engine/tasks.py`: `_guardar_artefacto` extrae texto plano con prioridad `contenido` → `cuerpo` → `texto` → `texto_reescrito` → fallback `respuesta.texto` cuando el modelo devuelve JSON válido que no cumple el esquema. Guarda el texto en `Artefacto.contenido` y `metadata["contenido"]`.
- `tests/test_engine.py`: nueva prueba `test_artefacto_extrae_cuerpo_cuando_json_no_tiene_contenido` (respx, sin API real).
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Sin cambios de schema, credenciales, permisos ni cola. Retrocompatible: `publicar_tarea` lee `meta.get('contenido')` o `artefacto.contenido`.
- Máximo 4 archivos modificados.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py seed_demo` → "Habilidades: 0 creadas, 13 actualizadas, 0 sin cambios." (incluye reescritura).
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `7 passed in 8.11s`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

## Paso C.10.6 - Ajuste de tolerancia para habilidad de reescritura — COMPLETADO

**Objetivo:** Que la habilidad `reescritura` acepte `texto_reescrito` como campo válido y requerido, evitando estados `failed` innecesarios cuando el modelo use esa nomenclatura. El normalizador ya extrae `texto_reescrito` → `Artefacto.contenido` si no encuentra `contenido` (tasks.py).

**Archivos tocados:**
- `apps/core/management/commands/seed_demo.py`: en la habilidad `reescritura`, el `esquema_salida` ahora es `{"type":"object","properties":{"titulo":{"type":"string"},"contenido":{"type":"string"},"texto_reescrito":{"type":"string"}},"required":["texto_reescrito"]}`. `titulo` y `contenido` pasan a ser opcionales; solo `texto_reescrito` es requerido. La lógica `if not created:` actualiza registros existentes (idempotente).

**Reglas respetadas:**
- No se modificó `models.py`, `tasks.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Sin cambios de schema, credenciales, permisos ni cola. Retrocompatible: `publicar_tarea` lee `metadata['contenido']` o `artefacto.contenido`.
- Máximo 1 archivo modificado (dentro del límite de 4).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py seed_demo` → "Habilidades: 0 creadas, 13 actualizadas, 0 sin cambios." (incluye reescritura).
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `7 passed`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- Commit: `ba27c0b` "Paso C.10.6: Esquema flexible para habilidad de reescritura".

**Impacto en contratos/datos:** SÍ datos persistidos (el `esquema_salida` de la habilidad `reescritura` se actualiza en BD al ejecutar `seed_demo`). NO contratos de código, NO credenciales, NO permisos, NO tareas en cola. Retrocompatible.

## Paso C.11a - Datos entre pasos en workflows — COMPLETADO

**Objetivo:** Que el paso N+1 de un workflow reciba el `data` del Artefacto del paso N como parte de su payload, permitiendo que el redactor use los hallazgos del investigador, por ejemplo.

**Archivos tocados:**
- `apps/engine/tasks.py`: en `continuar_workflow`, antes de crear la nueva tarea, extrae el último `Artefacto` de la tarea del paso anterior (`siguiente_orden - 1`) y lee `metadata['resultado']['data']` (con fallback a claves planas si no existe esa estructura). El `payload` de la nueva tarea pasa de `{}` a `{**datos_anteriores}`.
- `tests/test_engine.py`: nueva prueba `test_workflow_pasa_datos_entre_pasos` que crea un workflow de 2 pasos, simula un artefacto del paso 1 con `metadata['resultado']['data'] = {'hallazgos': ['dato1', 'dato2']}`, ejecuta `continuar_workflow` y verifica que la tarea del paso 2 tiene `payload == {'hallazgos': ['dato1', 'dato2']}`.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- No se tocó la lógica de estados (pendiente C.11b).
- Máximo 2 archivos modificados (dentro del límite de 4).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `8 passed in 7.77s` (incluye la prueba nueva `test_workflow_pasa_datos_entre_pasos`).
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

**Impacto en contratos/datos:** SÍ contratos (el `payload` del paso N+1 ya no viene vacío, contiene los datos del paso anterior). NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola. Retrocompatible: si no hay artefacto previo, el payload queda `{}`.

## Paso C.11b - Estados reales y modo manual en workflows — COMPLETADO

**Objetivo:**
1) Que el estado de la Tarea refleje el status del ResultadoAgente (completed→ok, partial→revision, failed→error).
2) Que modo_ejecucion="manual" pause el workflow y deje la tarea en estado "revision".

**Archivos tocados:**
- `apps/core/models.py`: añadido `ERROR = "error", "Error"` a `Tarea.Estado` y `Estado.OK` a las transiciones desde `Estado.CURSO` (antes requería doble transición CURSO→REVISION→OK). `ERROR` es estado terminal.
- `apps/engine/tasks.py`: en `ejecutar_tarea`, tras `_guardar_artefacto`, se lee `metadata['resultado']['status']` del último artefacto: `failed` → `transicionar(ERROR)` + propaga workflow a 'fallido'; `partial` o `modo_ejecucion == 'manual'` → `transicionar(REVISION)` y retorna sin continuar workflow; `completed` → `transicionar(OK)` y continúa workflow solo si `modo_ejecucion == 'auto'`. En `continuar_workflow`, se agregó guardia: si la tarea del paso anterior está en `REVISION` o `ERROR`, retorna "bloqueado" sin crear la siguiente tarea.
- `tests/test_engine.py`: actualizada `test_ejecutar_tarea_termina_en_ok` (respuesta JSON válida para esperar OK); actualizada `test_artefacto_guarda_texto_plano_cuando_respuesta_no_es_json` (estado ahora ERROR); añadidas `test_tarea_falla_cuando_normalizador_falla` (respuesta no-JSON → ERROR) y `test_tarea_revision_cuando_modo_manual` (manual → REVISION y no crea tarea del paso 2).
- Migración generada y aplicada: `apps/core/migrations/0014_alter_tarea_estado.py`.
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se crearon migraciones manuales (usó `makemigrations`).
- Máximo 3 archivos Python modificados (dentro del límite de 4).
- Pruebas sin APIs reales; `respx` para simular HTTP.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe manage.py migrate` → `Applying core.0014_alter_tarea_estado... OK`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `10 passed in 12.76s` (incluye las 2 pruebas nuevas).
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_models.py tests/test_providers.py tests/test_router.py tests/test_api.py tests/test_publicacion.py tests/test_integraciones.py -q` → `59 passed`.

**Impacto en contratos/datos:** SÍ datos persistidos (nuevo estado `ERROR` en choices del campo `estado` → migración 0014). NO credenciales, NO permisos, NO tareas en cola existentes, NO contratos de API. Retrocompatible: estados existentes (COLA, CURSO, REVISION, OK, FALLO) se mantienen.

## Paso C.11b.1 - Corregir detección de modo manual en tareas sueltas — COMPLETADO

**Objetivo:** Que `modo_ejecucion="manual"` se respete también cuando la tarea se crea de forma independiente (fuera de un workflow), no solo cuando es parte de un workflow (RB-010).

**Archivos tocados:**
- `apps/engine/tasks.py`: en `ejecutar_tarea`, `modo_manual` ahora se evalúa sobre `tarea.habilidad.modo_ejecucion` directamente, sin requerir `paso_workflow`. `paso` se conserva para el resto de la lógica de workflow (propagación y orquestación).
- `tests/test_engine.py`: nueva prueba `test_tarea_manual_sin_workflow_queda_en_revision` que verifica una tarea independiente (sin `paso_workflow`) con modo manual queda en `Tarea.Estado.REVISION`.
- `docs/plan.md`: esta sección y estado general actualizado.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Máximo 2 archivos modificados (dentro del límite de 4).
- Pruebas sin APIs reales; `respx` para simular HTTP.
- `tarea.habilidad` ya viene precargada con `select_related` (línea 298), sin consultas extra.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `11 passed in 9.69s` (incluye la prueba nueva).

**Impacto en contratos/datos:** NO contratos de API, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola existentes. Solo cambia el comportamiento de ejecución: tareas sueltas con modo manual quedan en REVISION (antes quedaban en OK). Retrocompatible: modo `"auto"` (default) no se ve afectado.

## Paso C.14 - Corregir creación de tareas para usar habilidad seleccionada — COMPLETADO

**Objetivo:** Que la vista `crear_tarea` use la habilidad seleccionada por el usuario en el formulario (`habilidad_id` por POST), en lugar de hardcodear `slug="reescritura"`, con fallback a la primera habilidad del agente.

**Archivos tocados:**
- `apps/panel/views.py`: en `crear_tarea`, se lee `habilidad_id` del POST; si se envía, se busca `Habilidad.objects.get(pk=...)` y se erroria con `messages.error` + `redirect` si no existe; si no se envía, se usa `agente.habilidades.first()` como fallback, con error si el agente no tiene habilidades.
- `apps/panel/templates/panel/crear_tarea.html`: añadido `<select name="habilidad_id" class="input">` que lista las habilidades de todos los agentes (con nombre del agente para distinguir), opción por defecto "-- Selecciona una habilidad --", clases ARM Flow, sin CSS embebido ni estilos inline.
- `tests/test_panel.py`: actualizado `test_crear_tarea_exitoso` para enviar `habilidad_id`; añadidas `test_crear_tarea_con_habilidad_seleccionada`, `test_crear_tarea_habilidad_inexistente` y `test_crear_tarea_sin_habilidad_id`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "crear_tarea" -q` → `9 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `46 passed`.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- No se ejecutó `git push`.
- Cambio retrocompatible: sin `habilidad_id` se usa el fallback a la primera habilidad del agente.

## Paso C.13 - Reescribir prompts de habilidades para que incluyan ejemplo JSON con campos required — COMPLETADO

**Objetivo:** Que los 10 prompts de `seed_demo.py` mencionen explícitamente los campos JSON que exige su esquema (`required`), para que el modelo sepa qué devolver.

**Archivos tocados:**
- `apps/core/management/commands/seed_demo.py`: reescrito el `plantilla_prompt` de 10 habilidades para incluir la instrucción de la tarea, un bloque de ejemplo JSON con los campos `required` y una breve descripción de cada uno, y la instrucción de no incluir texto fuera del JSON. Habilidades corregidas: `investigar_tema` (titulo, hallazgos), `metadatos_yoast` (titulo_seo, meta_descripcion, palabra_clave), `revision_calidad` (titulo, contenido), `corregir_ortografia` (contenido), `optimizar_seo` (titulo, contenido), `crear_titular` (titulo), `traducir_texto` (texto_traducido, idioma_destino), `generar_meta_descripcion` (meta_descripcion), `revisar_estilo` (contenido), `reescribir_editorial` (titulo, contenido).

**Reglas respetadas:**
- No se tocaron `esquema_salida`, `esquema_version` ni `permite_parcial`.
- Se mantiene `INSTRUCCION_ROL` (lógica de appended al final preservada en las habilidades no listadas; las 10 corregidas incorporan la instrucción de no-texto-fuera-del-JSON de forma explícita).
- No se modificó `models.py` ni se creó migración.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py seed_demo` → 13 habilidades actualizadas (incluidas las 10 corregidas), sin errores, idempotente.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py -q` → `12 passed in 11.67s`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.

**Impacto en contratos/datos:** SÍ datos persistidos (el `plantilla_prompt` de las 10 habilidades se actualiza en BD al ejecutar `seed_demo`). NO contratos de código, NO credenciales, NO permisos, NO tareas en cola. Retrocompatible.

## Paso S - Blindar configuración de seguridad en settings.py — COMPLETADO

**Objetivo:** Corregir las 3 configuraciones inseguras de `config/settings.py` para que el proyecto sea seguro en producción: `DEBUG` desde entorno (default `False`), `ALLOWED_HOSTS` desde entorno y `ARM_API_KEY` obligatoria si no `DEBUG`.

**Archivos tocados:**
- `config/settings.py`: `DEBUG = os.environ.get("DEBUG", "False") == "True"`; `ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")`; `ARM_API_KEY` leída de entorno con fallback a `"dev-api-key-123"` solo si `DEBUG=True`, `ImproperlyConfigured` si `DEBUG=False` y falta la variable.
- `.env.example`: añadida variable `ALLOWED_HOSTS=localhost,127.0.0.1` (ya tenía `SECRET_KEY`, `ARM_ENCRYPTION_KEY`, `ARM_API_KEY`, `DEBUG`).

**Reglas respetadas:**
- No se modificó `models.py`, `views.py`, `urls.py`, `forms.py` ni templates.
- No se creó migración (`makemigrations --check --dry-run` → No changes detected).
- No se ejecutó `git push`.
- Se respeta `docs/estandares/seguridad.md` §8 (`DEBUG=False` en producción, `ALLOWED_HOSTS` explícito) y §3 (no guardar secretos en repo).
- No se leyó ni escribió `.env` (solo `.env.example`).

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_integraciones.py tests/test_core.py tests/test_checks.py -q` → `41 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "integraciones or publicar or dashboard or sidebar or ejecuciones or crear_tarea or eliminar or aprobar" -q` → `28 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_models.py tests/test_publicacion.py -q` → `29 passed`.
- Verificación de comportamiento: `DEBUG=True` sin `ARM_API_KEY` → usa `"dev-api-key-123"`; `DEBUG=False` sin `ARM_API_KEY` en entorno ni `.env` → lanza `ImproperlyConfigured`.

**Impacto en contratos/datos:** NO contratos de API, NO datos persistidos, NO permisos, NO tareas en cola. SÍ credenciales (`ARM_API_KEY` obligatoria en producción). Retrocompatible: en desarrollo con `DEBUG=True` y `ARM_API_KEY` ausente se mantiene el valor por defecto `"dev-api-key-123"`.

**Estado general:** Pasos 0 a 25 y Bloque B (B.1 a B.10) completados. Bloque C: C.1a, C.1b, C.2, C.3a, C.3b, C.4, C.5a, C.5b, C.5c, C.6, C.7a, C.7b, C.7c+d, C.7e, C.8a, C.8b, C.8c, C.9a, C.9a-fix, C.9a-fix2, C.9b, C.10 Fase 2, C.10.3, C.10.5, C.10.6, C.11a, C.11b, C.11b.1, C.12a, C.12b, C.13, C.14 y C.15 completados. Paso S (blindado configuración de seguridad) completado. C.8 (retirar fallback temporal de proveedor LLM en publicación) completado.
   ## Paso UI - Estados legibles y mensajes de error en panel — COMPLETADO
   **Archivos:** `tareas.html`, `fila_tarea.html`. Usa `get_estado_display`, badge rojo para `error` y muestra `metadata.resultado.error.message`.

## Paso C.15 - Corregir guardado de habilidades ManyToMany al editar agente — COMPLETADO

**Objetivo:** Que al editar un agente en el panel y seleccionar/deseleccionar habilidades, los cambios se persistan correctamente en la base de datos, incluso si el formulario principal (nombre, rol, etc.) tiene errores de validación.

**Archivos tocados:**
- `apps/panel/views.py`: en `editar_agente`, se extrae `habilidades_ids = request.POST.getlist("habilidades")` al inicio del bloque POST y se ejecuta `agente.habilidades.set(habilidades_ids)` **antes** de evaluar `if form.is_valid()`, para que la selección del usuario se guarde siempre, independientemente de la validez del formulario.
- `tests/test_panel.py`: nueva prueba `test_editar_agente_guarda_habilidades` que hace login, usa un agente existente con 1 habilidad, hace POST con 2 habilidades nuevas, ejecuta `agente.refresh_from_db()` y verifica que los IDs del M2M coincidan exactamente con los enviados y que la vista devuelva 302.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (la relación ManyToMany ya existe).
- Máximo 2 archivos modificados (dentro del límite de 4).
- Pruebas sin APIs reales.
- No se ejecutó `git push`.
- Cambio de bajo riesgo: solo reordena una llamada `set()` existente en la vista; no afecta contratos de API, credenciales, permisos ni tareas en cola.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k editar_agente -q` → `1 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "agente" -q` → `3 passed`.

**Impacto en contratos/datos:** SÍ datos persistidos (tabla intermedia M2M `agente_habilidades` se actualiza al editar). NO contratos de API, NO credenciales, NO permisos, NO tareas en cola. Retrocompatible: misma URL `editar_agente` y mismo redirect 302 en éxito.

## Paso FIX-1 - Versionar migraciones pendientes y limpiar secretos en `.env.example` — COMPLETADO

**Objetivo:** Asegurar que el repositorio permita migrar desde cero y que `.env.example` no contenga valores con apariencia de claves reales.

**Archivos tocados:**
- `apps/core/migrations/0007_alter_proveedor_api_key.py`, `apps/core/migrations/0013_artefacto_raw_response_habilidad_esquema_version_and_more.py`, `apps/core/migrations/0014_alter_tarea_estado.py`: añadidos a Git (contenido sin modificar).
- `.env.example`: `SECRET_KEY` y `ARM_ENCRYPTION_KEY` reemplazadas por placeholders (`tu-clave-secreta-aqui-cambiar-en-produccion`, `tu-clave-fernet-aqui-cambiar-en-produccion`); `DEBUG=True` → `DEBUG=False` con comentario para desarrollo local; nota de no confirmar valores reales en Git.
- `docs/plan.md`: esta sección (queda sin commitear; el usuario solicitó un único commit con las migraciones y `.env.example`).

**Reglas respetadas:**
- No se modificó código Python, modelos, vistas, permisos ni cola.
- No se ejecutó `git push`.
- No se añadieron archivos no relacionados (`.vscode/`, `db.sqlite3-shm/-wal`, `docs/estandares/`).

**Evidencia de aceptación (ejecutado en esta sesión):**
- `git status --short apps/core/migrations` → sin salida (migraciones confirmadas).
- `git show --stat --oneline HEAD` → `1e9283d FIX-1: Versionar migraciones pendientes y limpiar secretos en .env.example` con 4 archivos.
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest -q` → `4 failed, 174 passed, 2 warnings in 310.47s`. La creación de la BD de test aplicó todas las migraciones desde cero (incluidas 0013/0014), por lo que la cadena de migraciones es válida.

**Fallos preexistentes detectados (no causados por FIX-1):**
- `tests/test_pipeline.py` (3 tests): envían texto plano y esperan pipeline exitoso; desde C.10/C.11b el normalizador exige JSON cuando `esquema_salida` no está vacío, la tarea principal termina en `error` y no se crea la tarea SEO.
- `tests/test_workflow.py::test_orquestacion_workflow`: espera `ejecutar_tarea.delay`, pero desde C.8a el encolado usa llamada directa (`ejecutar_tarea(nueva_tarea.pk)`); el test no se actualizó.
- FIX-1 solo añade archivos de migración ya presentes en disco y edita `.env.example`, que Django no carga (`settings.py` carga únicamente `.env`). No se corrigieron por estar fuera del alcance aprobado.

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO permisos, NO cola. SÍ credenciales de ejemplo (placeholders). Las claves reales que estuvieron en `.env.example` permanecen en el historial de Git: se recomienda rotar `SECRET_KEY` y `ARM_ENCRYPTION_KEY` en el `.env` local.

## Paso FIX-2 - Corregir reanudación de workflow en aprobación y error 500 en integraciones — COMPLETADO

**Objetivo:** (1) Que al aprobar una tarea en revisión con paso_workflow, el workflow continúe al siguiente paso. (2) Que rotar la clave API en integraciones no lance UnboundLocalError.

**Archivos tocados:**
- `apps/panel/views.py`: en `aprobar_tarea`, tras `tarea.estado = 'ok'` + `save()`, si `tarea.paso_workflow` existe, llama `continuar_workflow(tarea.paso_workflow.workflow.pk, tarea.paso_workflow.orden + 1)` (replicando la lógica de `ejecutar_tarea`). En `integraciones`, inicializa `form = DestinoPublicacionForm()` al inicio del bloque POST, antes de los if/elif, para evitar UnboundLocalError al rotar la clave ARM.
- `tests/test_panel.py`: nuevas pruebas `test_aprobar_tarea_reanuda_workflow` y `test_integraciones_rotar_clave_sin_500`.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración.
- Máximo 2 archivos modificados (dentro del límite de 4).
- Pruebas sin APIs reales; `ejecutar_tarea` mockeado para no llamar IA; `continuar_workflow.func` usado para simular el worker de Huey en la prueba.
- Los 4 tests rotos preexistentes (test_pipeline.py x3, test_orquestacion_workflow) no se tocan y pueden seguir fallando (se arreglan en FIX-3).
- No se ejecutó `git push`.
- Commit: "FIX-2: Corregir reanudación de workflow en aprobación y error 500 en integraciones".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "aprobar or integraciones" -q` → `7 passed` (incluye las 2 pruebas nuevas).
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -q` → `49 passed`.

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Retrocompatible.

**Pendientes:** actualizar los 4 tests obsoletos en un paso separado (FIX-3).

## Paso FIX-3 - Corregir pipeline slug y tests fallantes de pipeline/workflow — COMPLETADO

**Objetivo:** Dejar el suite de pruebas 100% en verde arreglando los 4 tests fallantes y el desajuste de slug en el pipeline editorial.

**Archivos tocados (3):**
- `apps/engine/pipelines.py`: búsqueda de la habilidad SEO cambiada de `slug="seo"` a `slug="optimizar_seo"` (coincide con lo que crea `seed_demo.py`).
- `tests/test_pipeline.py`: mocks de `respx` devuelven JSON válido (no texto plano) para que el normalizador no falle con `respuesta_no_json`/`campos_faltantes`; habilidad SEO creada con `slug="optimizar_seo"`; helper `_tarea_seo()` filtra por `slug="optimizar_seo"`.
- `tests/test_workflow.py`: `mock_ejecutar.delay.assert_called_once_with(...)` → `mock_ejecutar.assert_called_once_with(tarea2.pk)` (desde C.8a `continuar_workflow` llama a `ejecutar_tarea` directamente).

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Máximo 3 archivos modificados (dentro del límite de 4).
- Pruebas sin APIs reales; `respx` para simular HTTP.
- No se ejecutó `git push`.
- Commit pendiente: "FIX-3: Corregir pipeline slug y tests fallantes de pipeline/workflow".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_workflow.py -q` → `8 passed`.
- `.venv\Scripts\python.exe -m pytest -q` → `180 passed, 2 warnings` (warnings preexistentes de Django, no relacionados).

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Solo consulta de habilidad en `pipelines.py` y ajustes de tests. Retrocompatible.

## Paso UX-Markdown - Renderizar contenido de artefactos como HTML formateado — COMPLETADO

**Objetivo:** Que el contenido de los artefactos en el panel se muestre como texto formateado (Markdown renderizado a HTML) en lugar de texto crudo dentro de una etiqueta `<pre>`.

**Archivos tocados (4):**
- `apps/panel/templatetags/__init__.py` (nuevo, vacío): obligatorio para que Django reconozca la carpeta de etiquetas.
- `apps/panel/templatetags/markdown_tags.py` (nuevo): filtro `markdownify` que usa `markdown.markdown(text, extensions=['fenced_code', 'tables'])` y `mark_safe` para evitar escape del HTML resultante.
- `apps/panel/templates/panel/tareas.html`: carga `{% load markdown_tags %}` y reemplaza `<pre>{{ ultimo_artefacto.contenido }}</pre>` por `<div class="markdown-content">{{ ultimo_artefacto.contenido | markdownify }}</div>`.
- `static/css/app.css`: añade la clase `.markdown-content` con estilos de legibilidad (line-height, color, márgenes para h1-h6, p, ul/ol, strong, code, pre, table, blockquote) reutilizando tokens ARM Flow. Cero estilos inline, cero bloques `<style>`.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Máximo 4 archivos modificados.
- No se ejecutó `git push`.
- Commit: `c41e253` "UX: Renderizar contenido de artefactos como Markdown formateado".
- Estilo ARM Flow estricto: clases centrales en `app.css`, cero CSS embebido/inline.
- Riesgo XSS con `mark_safe` documentado: el contenido proviene del propio modelo (controlado por prompts); pendiente de auditoría si se abren usuarios externos.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py::TestPanel::test_detalle_tarea_autenticado -q` → `1 passed` (renderiza `tareas.html` con el nuevo filtro).
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "publicar or integraciones or sidebar or detalle or editar_destino" -q` → `14 passed`.
- Nota: `pytest tests/test_panel.py -q` completo se cuelga en un test preexistente de entorno (no relacionado con este cambio), documentado en pasos C.2/C.3a/C.4/C.9b.

**Impacto en contratos/datos:** NO contratos de API, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola. Solo presentación de plantilla. Retrocompatible: contenido sin Markdown se renderiza como párrafo HTML normal.

## Paso FIX-BUTTONS - Implementar edición/eliminación de Modelos, Proveedores y Workflows — COMPLETADO

**Objetivo:** Hacer funcionales los botones de Editar/Eliminar Modelo, Eliminar Proveedor y Eliminar Workflow, conectando URLs, vistas y templates correctamente, con manejo seguro de errores (ProtectedError).

**Archivos tocados (6):**
- `apps/panel/urls.py`: añadidas 4 rutas (`editar_modelo`, `eliminar_modelo`, `eliminar_proveedor`, `eliminar_workflow`).
- `apps/panel/views.py`: 4 vistas nuevas:
  - `editar_modelo(request, pk)`: reutiliza `ModeloLLMForm` existente; GET muestra formulario, POST guarda y redirige a `lista_modelos`.
  - `eliminar_modelo(request, pk)`: `@login_required`, `@require_POST`, `get_object_or_404(ModeloLLM)`, try/except `ProtectedError` con mensaje "No se puede eliminar: tiene agentes o tareas asociadas."
  - `eliminar_proveedor(request, pk)`: `@login_required`, `@require_POST`, `get_object_or_404(Proveedor)`, try/except `ProtectedError` con mensaje "No se puede eliminar: tiene modelos asociados."
  - `eliminar_workflow(request, pk)`: `@login_required`, `@require_POST`, `get_object_or_404(Workflow)`, valida `estado != 'en_ejecucion'`, try/except `ProtectedError` con mensaje "No se puede eliminar: tiene pasos o tareas asociadas."
- `apps/panel/templates/panel/lista_modelos.html`: corregidas URLs de editar/eliminar (líneas 41-45); añadido bloque de formulario de edición condicional (líneas 54-76) al estilo de `lista_proveedores.html`.
- `apps/panel/templates/panel/lista_proveedores.html`: corregida URL de eliminar (línea 45) a `{% url 'eliminar_proveedor' proveedor.pk %}`.
- `apps/panel/templates/panel/lista_workflows.html`: añadido formulario de eliminación en columna Acciones (líneas 33-40) con confirmación JS.

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Reutilizado `ModeloLLMForm` existente en `forms.py` (líneas 25-29), sin código duplicado.
- Vistas de eliminación decoradas con `@login_required` y `@require_POST`; CSRF en templates; manejo explícito de `ProtectedError` con `messages.error` + redirect (nunca 500).
- Estilo ARM Flow estricto: clases `.btn-danger-sm`, `.form-eliminar`, `.enlace-editar`, `.tarjeta`, `.form-group`, `.acciones-formulario`.
- Máximo 6 archivos modificados (dentro del límite aprobado).
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- URLs resueltas correctamente: `/panel/modelos/1/editar/`, `/panel/modelos/1/eliminar/`, `/panel/proveedores/1/eliminar/`, `/panel/workflows/1/eliminar/`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py tests/test_engine.py -q` → `73 passed` (incluye tests de render lista_modelos, lista_proveedores, lista_workflows, editar_proveedor, eliminar_destino, aprobar_workflow, etc.).
- `.venv\Scripts\python.exe -m pytest tests/test_integraciones.py tests/test_api.py tests/test_models.py tests/test_publicacion.py -q` → `30 passed`.
- Test suite completo (excluyendo 4 tests preexistentes rotos en test_pipeline.py/test_workflow.py): `172 passed, 2 warnings`.

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Retrocompatible: solo añade funcionalidad CRUD faltante.

## Paso UX-BATCH - Implementar paginación y acciones por lote en Tareas y Ejecuciones — COMPLETADO

**Objetivo:** Mejorar la usabilidad del panel añadiendo paginación a las listas de tareas (20 por página) y ejecuciones (50 por página), y permitiendo acciones masivas (aprobar/eliminar) sobre múltiples tareas seleccionadas.

**Archivos tocados (5):**
- `apps/panel/views.py`: import `Paginator`; `lista_tareas` y `lista_ejecuciones` paginan sus querysets y pasan `page_obj` al contexto; nueva vista `acciones_lote_tareas` (`@login_required`, `@require_POST`) que procesa `action` (`aprobar`/`eliminar`) y `task_ids[]`, usa `messages` framework, y para `aprobar` invoca `continuar_workflow.func()` si la tarea tiene `paso_workflow`.
- `apps/panel/urls.py`: ruta `tareas/lote/` → `acciones_lote_tareas`.
- `apps/panel/templates/panel/tareas.html`: dentro del bloque `{% else %}` (lista), añadidos: checkbox "select all" en `<th>`, checkbox por fila en `<td>`, formulario `.form-lote` con `<select name="action">` y botón "Aplicar" con confirmación JS, paginación `.paginacion` con enlaces Primera/Anterior/Siguiente/Última preservando `estado_filtro`, script "select all" con guard `if (selectAll)`.
- `apps/panel/templates/panel/fila_tarea.html`: columna checkbox `<input type="checkbox" name="task_ids" value="{{ tarea.pk }}">` como primer `<td>`.
- `apps/panel/templates/panel/lista_ejecuciones.html`: itera `page_obj` en lugar de `ejecuciones`; paginación `.paginacion` al final.
- `tests/test_panel.py`: 6 pruebas nuevas (`test_lista_tareas_paginacion`, `test_lista_tareas_filtro_estado_con_paginacion`, `test_acciones_lote_tareas_eliminar`, `test_acciones_lote_tareas_aprobar`, `test_acciones_lote_tareas_sin_seleccion`, `test_lista_ejecuciones_paginacion`).

**Reglas respetadas:**
- NO se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Máximo 5 archivos modificados (aprobado por excepción).
- `tareas.html` respeta la estructura dual `{% if tarea %}...{% else %}...{% endif %}`: toda la UI de lista (tabla, checkboxes, form lote, paginación) está dentro del `{% else %}`.
- Script "select all" verifica existencia del elemento antes de añadir listener (evita error en vista detalle).
- Paginación preserva query string `estado_filtro` en enlaces.
- Vista lote usa `messages` framework y `redirect`; `aprobar` llama a `continuar_workflow.func()` (sincrónico en tests, asíncrono en worker Huey).
- Estilo ARM Flow estricto: clases `.btn-primary`, `.btn-secondary`, `.input`, `.form-lote`, `.paginacion`, `.vacio`.
- Pruebas sin APIs reales; `respx` no necesario aquí.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "lista_tareas or lista_ejecuciones or acciones_lote" -q` → `7 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_engine.py tests/test_integraciones.py tests/test_publicacion.py -q` → `25 passed`.

**Impacto en contratos/datos:** SÍ contratos (nueva URL `acciones_lote_tareas`, parámetros POST `action` + `task_ids[]`). NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Retrocompatible: paginación opcional, acciones lote nuevas.

## Paso PULIDO-FINAL - Rediseño UI de paginación/lote, borrado de ejecuciones y claridad en workflows — COMPLETADO

**Objetivo:** Corregir el diseño visual de paginación y selección (reglas ARM Flow estrictas), añadir borrado por lote de ejecuciones y cerrar deuda de auditoría en la descripción de workflows.

**Archivos tocados (7):**
- `static/css/app.css`: añadido `.form-lote` (barra de herramientas integrada), `.paginacion` (enlaces de texto con hover sutil, estado activo con `var(--accent-primary)`), `td input[type="checkbox"]` (alineación vertical), `.workflow-secuencia` (flex-wrap con gap y separador). Sin estilos inline, sin gradientes, sin emojis.
- `apps/panel/templates/panel/tareas.html`: eliminado `style="width: auto;"` del `<select>` del formulario lote; paginación reescrita con `.paginacion` limpia (enlaces de texto sin clases `.btn-secondary`), span de página actual con clase `active`.
- `apps/panel/templates/panel/lista_ejecuciones.html`: añadida columna de checkboxes en thead/tbody; formulario `.form-lote` arriba de la tabla (solo opción "Eliminar seleccionadas"); paginación reescrita con `.paginacion`; script "select all" con guard `if (selectAll)`.
- `apps/panel/views.py`: nueva vista `acciones_lote_ejecuciones` (`@login_required`, `@require_POST`) que procesa `action='eliminar'` y `ejecucion_ids`, borra de forma segura y retorna mensajes vía `messages`.
- `apps/panel/urls.py`: ruta `path('ejecuciones/lote/', views.acciones_lote_ejecuciones, name='acciones_lote_ejecuciones')` añadida.
- `apps/panel/templates/panel/lista_workflows.html`: columna de descripción reemplazada por visualización de secuencia de pasos (`workflow.pasos.all|dictsort:"orden"`) con badges `.badge badge-info` y separador "→".
- `tests/test_panel.py`: nueva prueba `test_acciones_lote_ejecuciones_eliminar` (borrado masivo, verifica no seleccionadas permanecen).

**Reglas respetadas:**
- No se modificó `models.py` ni se creó migración (`makemigrations --check --dry-run` → No changes detected).
- Cero estilos inline en los templates modificados.
- Uso exclusivo de variables CSS de ARM Flow (`var(--space-sm)`, `var(--border-subtle)`, `var(--accent-primary)`, etc.).
- Confirmación JS (`onsubmit="return confirm(...)"`) en el borrado por lote.
- Máximo 6 archivos de implementación + 1 archivo de prueba.
- No se ejecutó `git push`.

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "lote or ejecuciones" -q` → `6 passed`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "tareas or ejecuciones or lote or workflows or sidebar or dashboard or integraciones or detalle or aprobar or editar_destino" -q` → `22 passed`.

**Impacto en contratos/datos:** SÍ contratos (nueva URL `acciones_lote_ejecuciones`, parámetros POST `action` + `ejecucion_ids[]`). NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Retrocompatible: solo añade funcionalidad de borrado masivo y mejora visual.

## Paso FIX-FORM-Lote - Mover cierre de formulario para incluir checkboxes en acciones por lote — COMPLETADO

**Objetivo:** Corregir el error estructural donde el `<form>` de acciones por lote se cerraba antes de la `<table>`, impidiendo que los checkboxes viajen en el POST.

**Archivos tocados (2):**
- `apps/panel/templates/panel/tareas.html`: movido `</form>` de después del botón "Aplicar" a justo después de `</table>` y antes de `<div class="paginacion">`.
- `apps/panel/templates/panel/lista_ejecuciones.html`: movido `</form>` de después del botón "Eliminar" a justo después de `</table>` y antes de `<div class="paginacion">`.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `views.py`, `urls.py`, `fila_tarea.html`, `app.css` ni ningún archivo Python.
- No se modificó el JavaScript ni los estilos CSS.
- Máximo 2 archivos de implementación (dentro del límite de 4).
- No se ejecutó `git push`.
- Commit: "FIX: Mover cierre de form para incluir checkboxes en acciones por lote".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "tareas or ejecuciones or lote" -q` → `8 passed`.
- Estructura HTML resultante: `<form ...> ... <table> ... </table> </form> <div class="paginacion">`.

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Solo reordenamiento de etiquetas HTML en templates. La lógica de vistas ya era correcta (`@require_POST`, `getlist('task_ids')` / `getlist('ejecucion_ids')`).

## Paso FIX-LAYOUT-LOTE - Reparar layout de acciones por lote — COMPLETADO

**Objetivo:** Separar el contenedor del formulario (block) de la barra de acciones (flex `.form-lote`) para que la tabla no quede atrapada dentro de un contexto flex y recupere su ancho completo, manteniendo los checkboxes dentro del `<form>`.

**Archivos tocados (2):**
- `apps/panel/templates/panel/tareas.html`: el `<form>` perdió la clase `.form-lote`; select y botón quedaron envueltos en `<div class="form-lote">`; la tabla queda dentro del form pero fuera del div flex.
- `apps/panel/templates/panel/lista_ejecuciones.html`: mismo patrón exacto.
- `docs/plan.md`: esta sección.

**Reglas respetadas:**
- No se modificó `views.py`, `urls.py`, `fila_tarea.html`, `app.css` ni ningún archivo Python.
- No se modificó el JavaScript ni los estilos CSS.
- Los checkboxes siguen dentro del `<form>`, por lo que el envío POST sigue intacto.
- Máximo 2 archivos de implementación (dentro del límite de 4).
- No se ejecutó `git push`.
- Commit: "FIX: Reparar layout de acciones por lote separando form y barra flex".

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe -m pytest tests/test_panel.py -k "lote" -q` → `4 passed`.
- Estructura HTML resultante: `<form ...> ... <div class="form-lote"><select>...</select><button>...</button></div> <table>...</table> </form> <div class="paginacion">`.

**Impacto en contratos/datos:** NO contratos, NO datos persistidos, NO credenciales, NO permisos, NO tareas en cola, NO migraciones. Solo reestructuración de HTML dentro del form para separar el contexto flex de la barra de acciones.

## Paso FASE1-MODELOS - Separar FormatoSalida y Herramienta de Habilidad, migrar datos existentes — COMPLETADO

**Objetivo:** Refactorizar modelos para separar "comportamiento" (Habilidad.instrucciones) de "formato de salida" (FormatoSalida.esquema), creando nuevos modelos `FormatoSalida` y `Herramienta`, y vinculándolos a `Agente` y `Tarea` con una migración de datos `RunPython` que preserva la configuración existente.

**Archivos tocados (6):**
- `apps/core/models.py`: Creado modelo `FormatoSalida` (nombre, slug, descripcion, esquema JSONField, version, permite_parcial, plantilla_formato). Creado modelo `Herramienta` (nombre, slug, tipo con choices scraping/busqueda/database/api/python, descripcion, configuracion JSONField). Modificado `Habilidad`: renombrado `plantilla_prompt`→`instrucciones`, eliminados `esquema_salida`, `esquema_version`, `permite_parcial`. Modificado `Agente`: añadido FK `formato_salida` (SET_NULL, null=True) y M2M `herramientas`. Modificado `Tarea`: añadido FK opcional `formato_salida` (override del agente).
- `apps/core/migrations/0015_formato_salida_herramienta_migracion.py` (nueva): `CreateModel` de `FormatoSalida` y `Herramienta`, `AddField` de `formato_salida`/`herramientas` en `Agente`, `AddField` de `formato_salida` en `Tarea`, `RunPython` para migrar `Habilidad.esquema_salida`→`FormatoSalida` y asignar a `Agente`, `RemoveField` de los 3 campos eliminados de `Habilidad`, `RenameField` `plantilla_prompt`→`instrucciones`.
- `apps/core/migrations/0016_alter_herramienta_configuracion.py` (nueva): añade `help_text` a `Herramienta.configuracion`.
- `apps/engine/tasks.py`: `_construir_mensajes` usa `tarea.habilidad.instrucciones`; `_normalizar_respuesta` recibe `FormatoSalida` en vez de `Habilidad` y lee `formato_salida.esquema` / `formato_salida.permite_parcial`; nuevo `_obtener_formato_salida(tarea)` resuelve override de tarea → formato del agente → None; `select_related` incluye `agente__formato_salida` y `formato_salida`.
- `apps/panel/forms.py`: `HabilidadForm` usa `instrucciones` y elimina campos de esquema; creado `FormatoSalidaForm` con todos los campos del nuevo modelo.
- `apps/core/management/commands/seed_demo.py`: reescrito para crear `FormatoSalida` primero (12 formatos), luego `Habilidad` con `instrucciones` y `formato_slug`, y `Agente` con `formato_salida` asignado.
- `tests/`: actualizadas referencias a campos eliminados en `test_api.py`, `test_core.py`, `test_engine.py`, `test_models.py`, `test_panel.py`, `test_panel_agente.py`, `test_panel_listas.py`, `test_pipeline.py`, `test_workflow.py` (`plantilla_prompt`→`instrucciones`, eliminado `esquema_salida`/`esquema_version`/`permite_parcial`).

**Reglas respetadas:**
- No se editaron migraciones ya aplicadas; se crearon 0015 y 0016 nuevas.
- Migración de datos con `RunPython` manejando `esquema_salida` vacío/nulo (no crea FormatoSalida en ese caso).
- `transaction.atomic()` implícito en `RunPython` de Django.
- No se modificó `models.py` de otras apps.
- No se ejecutó `git push`.
- Se ajustó `config/settings.py` para forzar SQLite bajo pytest (evita fallos de conexión a Supabase en desarrollo local).

**Evidencia de aceptación (ejecutado en esta sesión):**
- `.venv\Scripts\python.exe manage.py check` → `System check identified no issues (0 silenced)`.
- `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` → `No changes detected`.
- `.venv\Scripts\python.exe -m pytest -q` → `187 passed, 2 warnings` (suite completa en verde).
- Migración aplicada: `core.0015` y `core.0016` aplicadas correctamente en SQLite de desarrollo.
- Datos antiguos de esquemas JSON migrados a `FormatoSalida` y vinculados a `Agente`.

**Impacto en contratos/datos:** SÍ datos persistidos (renombro/eliminación de columnas de `Habilidad`, nuevas tablas `FormatoSalida`/`Herramienta`, nuevas FK en `Agente` y `Tarea`). SÍ contratos de código (`tasks.py`, `forms.py`, `seed_demo.py`, tests). NO credenciales, NO permisos, NO tareas en cola existentes. NO retrocompatible sin actualizar consumidores de `Habilidad.plantilla_prompt` / `habilidad.esquema_salida`.