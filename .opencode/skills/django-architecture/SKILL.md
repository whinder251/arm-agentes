---
name: django-architecture
description: Reglas de arquitectura Django de ARM Agentes (Fat Models, Thin Views, Smart Services). Úsala al crear o modificar modelos, vistas, formularios, URLs, templates o tareas Huey, y al decidir en qué app (core, panel, engine, agents) debe vivir cada pieza de código.
---

# Skill: Django Architecture & Best Practices

## Contexto
ARM Agentes es un proyecto Django modular. La arquitectura sigue el patrón "Fat Models, Thin Views, Smart Services". La lógica de negocio pesada (scraping, IA, tareas en cola) vive en `apps/engine`, no en las vistas.

## 1. Estructura de Aplicaciones (Apps)

El proyecto se divide en capas de responsabilidad. Respetar estos límites es obligatorio:

- **`apps/core`**: Modelos base, señales, managers personalizados y utilidades compartidas. No debe depender de `panel` ni `engine`.
- **`apps/panel`**: La capa de presentación web. Contiene `views.py`, `forms.py`, `urls.py` y `templates/`. Solo debe orquestar peticiones HTTP y renderizar templates.
- **`apps/engine`**: El motor de negocio. Aquí vive la lógica de extracción web, procesamiento de IA, tareas de Huey y servicios complejos.
- **`apps/agents`**: Configuración de agentes, habilidades y proveedores LLM.

## 2. Modelos (Rich Models)

Los modelos deben ser inteligentes y autocontenidos.

- **Métodos obligatorios**:
  - `__str__`: Debe ser descriptivo (ej. `f"{self.nombre} ({self.get_modo_busqueda_display()})"`).
  - `get_absolute_url`: Apuntar a la vista de detalle cuando exista (ej. `/investigacion/{pk}/`).
- **Propiedades (`@property`)**: Usar para cálculos derivados o estados lógicos (ej. `esta_activa`, `total_hallazgos`). No guardar en BD lo que se puede calcular.
- **Meta**: Definir `ordering` (ej. `['-creado_en']`) y `verbose_name`/`verbose_name_plural` en español.
- **Relaciones**:
  - Usar `related_name` descriptivo en ForeignKey (ej. `investigacion = ForeignKey(..., related_name='hallazgos')`).
  - Usar `on_delete=models.CASCADE` para dependencias fuertes, `PROTECT` para datos críticos.

## 3. Vistas (Thin Views)

Las vistas son controladores HTTP delgados.

- **Estilo**: Usar Function-Based Views (FBVs) con decoradores (`@login_required`, `@require_POST`).
- **Límite de complejidad**: Si una vista supera las 30-40 líneas o tiene lógica de negocio compleja, extraer esa lógica a una función en `apps/engine/services.py` o `apps/engine/investigaciones.py`.
- **Patrón PRG**: Siempre usar Post/Redirect/Get. Después de un POST exitoso, retornar `redirect(...)`, nunca `render(...)`.
- **Feedback**: Usar `django.contrib.messages` para notificaciones al usuario.
- **Prohibido**:
  - Llamadas directas a APIs externas (DuckDuckGo, OpenAI) desde la vista.
  - Queries complejas con múltiples joins en la vista (usar `select_related` en el manager o servicio).
  - Lógica de negocio (cálculos, transformaciones de datos).

## 4. Formularios (Forms)

La validación vive aquí, no en la vista.

- **Validación**: Usar `clean_<field>()` para campos individuales y `clean()` para validaciones cruzadas.
- **Mensajes de error**: Personalizar `error_messages` en los campos para que sean útiles en español.
- **Widgets**: Definir clases CSS en el `__init__` o en el `Meta.widgets`, nunca en el template.

## 5. URLs y Ruteo

- **Nomenclatura**: `snake_case` para los nombres de las URLs (ej. `name='crear_investigacion'`).
- **Namespaces**: Usar `app_name = 'panel'` en `urls.py` para evitar colisiones.
- **Estructura**: Mantener las URLs agrupadas por recurso (ej. todas las de investigación juntas).

## 6. Templates

- **Herencia**: Extender siempre de `base.html`.
- **Lógica**: Mínima. Usar template tags y filtros. Si necesitas lógica compleja, pásala desde la vista o usa un template tag personalizado.
- **Bloques**: Usar `{% block content %}` y `{% block extra_js %}` de forma consistente.
- **Inclusión**: Usar `{% include %}` para componentes reutilizables (ej. tarjetas, paginación).

## 7. Tareas en Segundo Plano (Huey)

- **Ubicación**: Todas las tareas deben vivir en `apps/engine/tasks.py`.
- **Diseño**: Las tareas deben ser idempotentes (poder ejecutarse varias veces sin efectos secundarios graves).
- **Manejo de errores**: Capturar excepciones específicas y loguearlas. No dejar que una tarea falle silenciosamente. Ver la skill `error-handling` para el patrón completo.
- **Argumentos**: Pasar IDs de objetos (ej. `investigacion_id`), no instancias completas, para evitar problemas de serialización y datos stale.

## 8. Checklist de Revisión de Arquitectura

Antes de commitear, verifica:
- [ ] ¿La vista tiene más de 30 líneas? → Mover lógica a `engine`.
- [ ] ¿El modelo tiene lógica de negocio? → Mover a `@property` o método.
- [ ] ¿Hay SQL crudo? → Usar ORM.
- [ ] ¿La URL está en `snake_case`?
- [ ] ¿El `related_name` del ForeignKey es claro?
- [ ] ¿La tarea de Huey usa IDs en lugar de instancias?
