---
description: Implementa un paso del plan con aprobación previa, estándares aplicables y tests
agent: build
---
Paso solicitado: $ARGUMENTS

Fase 1 — análisis, sin escribir código:
1. Lee `AGENTS.md` y la sección correspondiente de `docs/plan.md`.
2. Identifica qué estándares aplican y lee `docs/estandares/codigo.md`, `seguridad.md`, `.opencode/skills/design-linear-nod/SKILL.md` y/o `pruebas.md` según el alcance.
3. Inspecciona solo los archivos relacionados y sus pruebas; busca implementaciones reutilizables.
4. Responde en menos de 10 líneas: objetivo, archivos previstos (máximo 4 salvo autorización), estándares aplicables, riesgos y criterio de aceptación.
5. Señala explícitamente si el cambio afecta contratos, datos persistidos, credenciales, permisos, tareas en cola o compatibilidad.
6. No escribas código ni modifiques archivos en esta fase. Espera aprobación.

Fase 2 — solo después de mi aprobación:
1. Implementa únicamente el paso aprobado, con diffs mínimos.
2. Escribe o actualiza las pruebas pertinentes antes o junto al código. Nunca llames APIs reales; usa `respx` y fixtures.
3. Aplica los estándares consultados. Si una regla no puede cumplirse por una limitación del sistema actual, detente y explica el conflicto.
4. Ejecuta las pruebas relevantes y, como mínimo para cambios de código, `.venv\Scripts\python.exe -m pytest -q` y `.venv\Scripts\python.exe manage.py check`.
5. Si cambias modelos, revisa y aplica las migraciones necesarias y ejecuta `makemigrations --check --dry-run`.
6. Si una prueba falla, investiga la causa. Tras dos intentos fallidos de corrección, detente y explica la causa raíz.
7. No afirmes que verificaste UI visual, seguridad, rendimiento o producción si no ejecutaste la comprobación correspondiente.
8. Actualiza `docs/plan.md` con lo realizado, evidencia real y pendientes. No marques completado si el criterio no se ejecutó.
9. Entrega resumen de archivos, pruebas, migraciones, riesgos y pendientes. No avances al paso siguiente.
10. No ejecutes `git push`.
