---
description: Revisión técnica de calidad, seguridad y regresiones antes del commit; no modifica archivos
agent: revisor
subagent: false
---
Estado del repositorio:

!`git status --short`

Resumen del diff:

!`git diff --stat`

Diff completo:

!`git diff`

Revisa los cambios contra:
- `AGENTS.md`
- `docs/plan.md`
- `docs/estandares/codigo.md`
- `docs/estandares/seguridad.md`
- `docs/estandares/diseno-ui.md` si hay cambios de interfaz
- `docs/estandares/pruebas.md`

No modifiques archivos. No ejecutes `git push`.

Entrega hallazgos ordenados por gravedad (crítico, alto, medio, bajo), indicando archivo, línea, escenario de riesgo y corrección mínima. Distingue defectos confirmados de riesgos potenciales y de recomendaciones.

Comprueba, cuando aplique:

1. Arquitectura y mantenibilidad
   - lógica de negocio en vistas o templates;
   - duplicación, dependencias circulares, abstracciones innecesarias;
   - contratos o comportamientos existentes que puedan romperse;
   - migraciones incompatibles o cambios de datos sin estrategia.

2. Rendimiento e integridad
   - consultas N+1, consultas repetidas y ausencia de paginación;
   - escrituras no atómicas en cuotas, contadores y estados;
   - condiciones de carrera y transacciones largas;
   - tareas no idempotentes, reintentos ilimitados o duplicación de efectos externos.

3. Seguridad
   - secretos o datos sensibles en código, respuestas, fixtures o logs;
   - rutas sin autenticación/autorización o controles solo en frontend;
   - acceso a objetos ajenos (IDOR/BOLA) y aislamiento de proyecto insuficiente;
   - validación débil de entradas y salidas;
   - SSRF, redirecciones o URLs externas sin control;
   - CSRF, XSS, SQL injection, path traversal y carga de archivos insegura;
   - herramientas de agentes sin permisos explícitos;
   - límites ausentes de tokens, coste, tiempo, tamaño, frecuencia o concurrencia;
   - errores que revelen información interna.

4. Integraciones y workers
   - llamadas de red reales dentro de tests;
   - timeouts, manejo de errores o límites ausentes;
   - estados no persistidos o fallos no propagados;
   - autenticación de webhooks insuficiente;
   - secretos mezclados entre proveedores LLM e integraciones funcionales.

5. Pruebas
   - falta de casos negativos, permisos, límites, fallos y regresión;
   - mocks que ocultan comportamiento importante;
   - pruebas frágiles o dependientes de servicios reales;
   - migraciones no verificadas.

6. Interfaz, si aplica
   - CSS duplicado o embebido;
   - clases/tokens inconsistentes con ARM Flow;
   - estados vacíos, carga, error o éxito ausentes;
   - formularios sin labels o errores claros;
   - problemas responsive o accesibilidad observables en el código.

No supongas que un riesgo es una vulnerabilidad confirmada sin evidencias. No propongas refactors extensos. No marques el diff como aprobado si no pudiste revisar un área: indícala como no verificada.
