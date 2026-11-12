---
description: Revisión de calidad antes del commit, sin editar archivos
agent: revisor
subagent: false
---
Estado del repo:

!`git status --short`

!`git diff --stat`

Diff completo:

!`git diff`

Revisa contra AGENTS.md y docs/plan.md. Reporta hallazgos ordenados por gravedad,
con archivo y línea. Busca dependencias no autorizadas, llamadas de red en los
tests, claves escritas en el código, estados que no se persisten, escrituras no
atómicas en el contador de cuota y falta de tests. No propongas parches largos:
señala el problema y la corrección mínima. No modifiques nada.