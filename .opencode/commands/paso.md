---
description: Implementa un paso del plan con aprobación previa y tests
agent: build
---
Paso solicitado: $ARGUMENTS

Fase 1, sin escribir código:
1. Lee AGENTS.md y la sección de ese paso en docs/plan.md.
2. Responde con menos de 10 líneas: archivos que vas a crear o modificar, máximo 4,
   y el criterio de aceptación. Si ves un riesgo grave, menciónalo.
3. Detente y espera mi OK. No escribas código en esta fase.

Fase 2, solo tras mi OK:
1. Implementa únicamente ese paso, con diffs mínimos.
2. Escribe los tests del paso. Nunca llames a APIs reales: usa respx y fixtures.
3. Ejecuta python -m pytest -q y python manage.py check.
4. Si un test falla, corrige. Tras dos intentos fallidos, detente y explica la
   causa raíz antes de seguir.
5. Actualiza docs/plan.md: marca el estado del paso y anota lo pendiente.
6. Entrega un resumen de 5 líneas. No avances al paso siguiente.