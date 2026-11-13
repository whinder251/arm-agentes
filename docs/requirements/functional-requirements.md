# Requisitos Funcionales de ARM

## Módulo Núcleo (CORE)
- RF-CORE-001: Persistir Tarea con estados cola, curso, revision, ok, fallo [IMPL]
- RF-CORE-002: Tarea referencia Agente (FK) y Habilidad (FK obligatoria) [IMPL]
- RF-CORE-003: Payload de Tarea guarda texto, keyword opcional, instrucciones opcionales [IMPL]
- RF-CORE-004: Proveedor almacena nombre, base_url, api_key (cifrada), rpm, limite_diario, limite_tokens_diario [PARC]
- RF-CORE-005: ModeloLLM referencia Proveedor con model_id, prioridad, json_nativo, activo [IMPL]
- RF-CORE-006: Habilidad guarda nombre, slug, plantilla_prompt, esquema_salida (JSON válido), modo_ejecucion [PARC]
- RF-CORE-007: Agente guarda nombre, rol, temperatura, modelo FK, habilidades M2M [IMPL]
- RF-CORE-008: Artefacto versiona contenido generado con metadata JSON [IMPL]
- RF-CORE-009: Ejecucion registra modelo_usado, tokens_in, tokens_out, duración ms [IMPL]

## Módulo Agentes (AGT)
- RF-AGT-001: Crear, editar, eliminar agentes desde panel [IMPL]
- RF-AGT-002: Asignar habilidades a agente mediante tarjetas seleccionables [IMPL]
- RF-AGT-003: Configurar proveedor y modelo sin tocar admin Django [IMPL]
- RF-AGT-004: Plantillas de personalidad predefinidas [IMPL]
- RF-AGT-005: Control de temperatura 0-2 con slider [IMPL]
- RF-AGT-006: Validar esquema_salida como JSON válido antes de guardar [PENDIENTE]
- RF-AGT-007: Crear equipos de agentes [PROPUESTO]
- RF-AGT-008: Asignar agentes a equipos [PROPUESTO]

## Módulo Tareas (TSK)
- RF-TSK-001: Crear tarea desde panel con texto obligatorio [IMPL]
- RF-TSK-002: Asignar agente manualmente o automáticamente [IMPL]
- RF-TSK-003: Encolar tarea en Huey al crearla [IMPL]
- RF-TSK-004: Revisar tareas huérfanas periódicamente [IMPL]
- RF-TSK-005: Derivar título, meta, slug del texto reescrito [PARC]
- RF-TSK-006: Crear Workflow (secuencia de habilidades) [PROPUESTO]
- RF-TSK-007: Ejecutar Workflow con dependencias entre pasos [PROPUESTO]
- RF-TSK-008: Pausar ejecución si modo_ejecucion es 'manual' [PROPUESTO]

## Módulo Verificación (CHK)
- RF-CHK-001: Aplicar verificadores deterministas de estilo, hechos, SEO [IMPL]
- RF-CHK-002: Validar salida de modelo con Pydantic antes de guardar [IMPL]
- RF-CHK-003: Dejar en revision lo que no pasa verificador [IMPL]

## Módulo Aprobación (APR)
- RF-APR-001: Solicitar aprobación humana para acciones sensibles [PARC]
- RF-APR-002: Aprobar con HTMX sin recargar página [IMPL]
- RF-APR-003: Registrar usuario aprobador en metadata [IMPL]
- RF-APR-004: Configurar acciones como auto o manual [PROPUESTO]

## Módulo Publicación (PUB)
- RF-PUB-001: Publicar en WordPress vía API REST [PARC]
- RF-PUB-002: Generar sitemap XML [IMPL]
- RF-PUB-003: Botón "Publicar" en detalle de tarea aprobada [PROPUESTO]

## Módulo Integración (INT)
- RF-INT-001: Endpoint REST autenticado para recibir tareas externas [PROPUESTO]
- RF-INT-002: Webhook para notificar estado de tareas a sistemas externos [PROPUESTO]
- RF-INT-003: Plugin WordPress que consume API de ARM [PROPUESTO]

## Módulo Seguridad (SEC)
- RF-SEC-001: Cifrar api_key de proveedores en base de datos [PROPUESTO]
- RF-SEC-002: Leer configuraciones sensibles desde variables de entorno [PROPUESTO]
- RF-SEC-003: Autenticación de endpoints REST con token [PROPUESTO]

## Módulo Presupuesto (BUD)
- RF-BUD-001: Registrar tokens consumidos por tarea [IMPL]
- RF-BUD-002: Definir límite de tokens diario por proveedor [PROPUESTO]
- RF-BUD-003: Rechazar encolación si excede cuota [PROPUESTO]
- RF-BUD-004: Dashboard de consumo de tokens [PROPUESTO]