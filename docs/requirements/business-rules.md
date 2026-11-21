> **Nota**: Este documento describe el estado del proyecto en noviembre 2026 (pasos 0-23). Para el estado actual, consulta docs/plan.md.

# Reglas de Negocio de ARM

## AsignaciÃ³n y EjecuciÃ³n
- RB-001: Tarea solo se borra por POST con CSRF. GET devuelve 405. [IMPL]
- RB-002: No se elimina habilidad ni agente referenciados por tareas (PROTECT). [IMPL]
- RB-003: AsignaciÃ³n automÃ¡tica usa primer agente con modelo activo, ordenado por pk. [IMPL]
- RB-004: Keyword vacÃ­a no se incluye en payload. [IMPL]
- RB-005: Actividad de agente se deriva de modelo.activo. [IMPL]
- RB-006: Cuota se reserva antes de llamada al modelo. Si excede, tarea no se ejecuta. [IMPL]
- RB-007: TransiciÃ³n okâ†’revision se aplica con UPDATE directo. [PARC - deuda]
- RB-008: FK Habilidad de tarea estÃ¡ fijada al slug "reescritura". [PARC - contradicciÃ³n]
- RB-009: Sistema rechaza encolaciÃ³n si excede cuota diaria o RPM del proveedor. [PROPUESTO]
- RB-010: Si modo_ejecucion de habilidad es 'manual', flujo se pausa y genera tarea en revision. [PROPUESTO]
- RB-011: Workflow se ejecuta en orden. Paso N no se encola hasta que Paso N-1 estÃ© en ok. [PROPUESTO]
- RB-012: Equipo debe tener al menos un agente con modelo activo para aceptar Workflow. [PROPUESTO]

## Seguridad y Presupuesto
- RB-013: api_key se cifra antes de guardar en base de datos. [PROPUESTO]
- RB-014: LÃ­mite de tokens diario por proveedor es obligatorio. [PROPUESTO]
- RB-015: Usuario puede definir presupuesto mÃ¡ximo por tarea o por dÃ­a. [PROPUESTO]
- RB-016: Sistema corta ejecuciÃ³n automÃ¡ticamente al superar presupuesto. [PROPUESTO]

## IntegraciÃ³n
- RB-017: Endpoint REST requiere autenticaciÃ³n con token. [PROPUESTO]
- RB-018: Webhook notifica estado de tarea a URL configurada. [PROPUESTO]
- RB-019: Plugin WordPress puede crear tarea y consultar estado vÃ­a API. [PROPUESTO]
