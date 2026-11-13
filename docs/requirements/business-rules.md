# Reglas de Negocio de ARM

## Asignación y Ejecución
- RB-001: Tarea solo se borra por POST con CSRF. GET devuelve 405. [IMPL]
- RB-002: No se elimina habilidad ni agente referenciados por tareas (PROTECT). [IMPL]
- RB-003: Asignación automática usa primer agente con modelo activo, ordenado por pk. [IMPL]
- RB-004: Keyword vacía no se incluye en payload. [IMPL]
- RB-005: Actividad de agente se deriva de modelo.activo. [IMPL]
- RB-006: Cuota se reserva antes de llamada al modelo. Si excede, tarea no se ejecuta. [IMPL]
- RB-007: Transición ok→revision se aplica con UPDATE directo. [PARC - deuda]
- RB-008: FK Habilidad de tarea está fijada al slug "reescritura". [PARC - contradicción]
- RB-009: Sistema rechaza encolación si excede cuota diaria o RPM del proveedor. [PROPUESTO]
- RB-010: Si modo_ejecucion de habilidad es 'manual', flujo se pausa y genera tarea en revision. [PROPUESTO]
- RB-011: Workflow se ejecuta en orden. Paso N no se encola hasta que Paso N-1 esté en ok. [PROPUESTO]
- RB-012: Equipo debe tener al menos un agente con modelo activo para aceptar Workflow. [PROPUESTO]

## Seguridad y Presupuesto
- RB-013: api_key se cifra antes de guardar en base de datos. [PROPUESTO]
- RB-014: Límite de tokens diario por proveedor es obligatorio. [PROPUESTO]
- RB-015: Usuario puede definir presupuesto máximo por tarea o por día. [PROPUESTO]
- RB-016: Sistema corta ejecución automáticamente al superar presupuesto. [PROPUESTO]

## Integración
- RB-017: Endpoint REST requiere autenticación con token. [PROPUESTO]
- RB-018: Webhook notifica estado de tarea a URL configurada. [PROPUESTO]
- RB-019: Plugin WordPress puede crear tarea y consultar estado vía API. [PROPUESTO]