# ARM — Instrucciones generales para agentes de desarrollo

ARM es una plataforma modular de orquestación y ejecución de tareas mediante agentes de IA, con un panel tipo "Centro de Mando". El módulo actual está orientado a workflows, monitoreo y publicación de contenido, pero la arquitectura debe permitir incorporar otros módulos y casos de uso sin convertir el núcleo en una aplicación dependiente de SEO o WordPress.

## 1. Principios de trabajo

1. Conserva la arquitectura, convenciones y comportamiento existentes. Inspecciona el código relacionado antes de proponer cambios.
2. No reconstruyas componentes que ya existen. Busca primero modelos, servicios, utilidades, formularios, componentes UI y pruebas reutilizables.
3. Implementa el cambio mínimo que resuelva el requisito, sin sacrificar seguridad, integridad, legibilidad ni pruebas.
4. No inventes APIs, firmas, parámetros ni capacidades de dependencias. Comprueba la documentación o declara la incertidumbre.
5. No añadas dependencias sin justificar el problema, alternativas, impacto de mantenimiento y solicitar aprobación.
6. No hagas refactors amplios dentro de una tarea funcional pequeña.
7. No ocultes fallos con excepciones genéricas, valores por defecto silenciosos o estados de éxito falsos.
8. No afirmes que una prueba, comando, migración o verificación se ejecutó si no se ejecutó en esta sesión.
9. Si el código real contradice un documento, o dos documentos se contradicen, no lo resuelvas por intuición: infórmalo con archivo y línea, y propón una decisión. Mientras tanto, aplica la precedencia de la sección 2.

## 2. Documentación obligatoria

Consulta los estándares que correspondan al cambio:

- `docs/estandares/codigo.md`: Python, Django, modelos, servicios, consultas, workers, API y arquitectura.
- `docs/estandares/seguridad.md`: autenticación, autorización, credenciales, integraciones, archivos, agentes y despliegue.
- `.opencode/skills/design-linear-nod/SKILL.md`: tokens CSS, componentes, botones, formularios y anti-patrones visuales.
- `.opencode/skills/form-ux/SKILL.md`: buenas prácticas de UX para formularios (orden, valores por defecto, errores, estados).
- `docs/estandares/pruebas.md`: pruebas nuevas, cambios de comportamiento, regresión y verificación.
- `docs/requirements/business-rules.md`: reglas de negocio y su estado de implementación (`[IMPL]`, `[PARC]`, `[PROPUESTO]`).

`docs/estilo.md` es exclusivamente el conjunto de reglas para evaluar el contenido producido por los agentes (artículos, titulares y metadatos). No es el estándar de código ni la guía visual del panel.

Si un cambio afecta varias áreas, consulta todos los estándares pertinentes.

### Precedencia

Cuando dos fuentes se contradigan, aplica este orden y avisa del conflicto:

1. Instrucción explícita del usuario en la sesión actual.
2. Este archivo (`AGENTS.md`).
3. `docs/estandares/*.md`.
4. Skills de `.opencode/skills/`. Aportan detalle; nunca anulan los estándares ni este archivo.
5. `docs/plan.md`, `docs/requirements/*` y cualquier otro documento.

Para el aspecto visual, la fuente de verdad es el código: `static/css/app.css` prevalece sobre cualquier documento (ver sección 8).

## 3. Entorno y restricciones actuales

- Desarrollo local actual: Windows 11, PowerShell 5.1 y Python 3.12 dentro de `.venv`.
- Base de datos de desarrollo actual: SQLite en modo WAL.
- Cola actual: Huey con SqliteHuey.
- No introducir Docker, WSL, Redis, Celery, Celery Beat, Node, npm, LangChain o CrewAI en esta etapa.
- La fuente de verdad de las dependencias es `requirements.txt`. Dependencias base autorizadas: Django 5.2 LTS, Huey, httpx, Pydantic v2, python-dotenv, cryptography, pytest, pytest-django y respx.
- Según `docs/plan.md`, pasos posteriores añadieron `requests` (adaptadores de proveedores, `tool_executor` y motor de monitoreo), `markdown`, `trafilatura`, `duckduckgo-search`, `crawl4ai` y BeautifulSoup. Verifica `requirements.txt` antes de asumir qué hay instalado.
- Cliente HTTP: en un módulo existente, sigue el cliente que ya usa (hoy `requests` en el motor y los proveedores). No mezcles `requests` y `httpx` en el mismo módulo. Migrar de uno a otro requiere un paso aprobado.
- Una dependencia adicional requiere justificación y aprobación explícita.
- Las restricciones anteriores describen el entorno y la etapa actuales; no significan que ARM deba quedar limitado a SQLite en producción. La preparación para PostgreSQL y otros componentes de producción debe hacerse mediante un paso aprobado y documentado.

### Comandos PowerShell

Usa el intérprete del entorno virtual:

- Servidor: `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`
- Worker: `.venv\Scripts\python.exe manage.py run_huey`
- Tests: `.venv\Scripts\python.exe -m pytest -q`
- Comprobación: `.venv\Scripts\python.exe manage.py check`
- Migraciones: `.venv\Scripts\python.exe manage.py makemigrations`
- Verificar migraciones pendientes: `.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
- Aplicar migraciones: `.venv\Scripts\python.exe manage.py migrate`

No uses `&&`; ejecuta comandos PowerShell en líneas separadas. Cita rutas que contengan espacios. No uses `Get-Content` para leer archivos si está disponible una herramienta de lectura adecuada.

### Codificación de archivos

Todos los archivos de texto del repositorio son UTF-8 sin BOM. En PowerShell 5.1, `>`, `>>`, `Out-File` y `Add-Content` escriben UTF-16 por defecto, y leer UTF-8 sin `-Encoding UTF8` produce texto corrupto (por ejemplo `Ã¡` en lugar de `á`). Nunca escribas ni anexes archivos con esos comandos. Edita con la herramienta de edición de archivos. Tras modificar `docs/plan.md` o cualquier documento, comprueba que no aparecen caracteres corruptos.

## 4. Flujo obligatorio de implementación

1. Trabaja en un solo paso solicitado por vez.
2. Antes de escribir código, lee este archivo, la cabecera "Estado Actual" y la sección del paso pertinente de `docs/plan.md`, y los estándares aplicables. `docs/plan.md` es extenso: localiza la sección por su encabezado en lugar de leerlo completo.
3. Presenta un plan de menos de 10 líneas con archivos previstos (máximo 4 por cambio, salvo excepción aprobada), riesgos y criterios de aceptación.
4. Espera aprobación explícita antes de implementar.
5. Escribe o actualiza pruebas antes o junto con el código.
6. Los tests no deben llamar servicios externos reales. Simula HTTP con el mecanismo del módulo (`respx` para `httpx`, `unittest.mock.patch` para `requests`) y fixtures.
7. Ejecuta las verificaciones pertinentes. Como mínimo, antes de cerrar un cambio de código ejecuta `pytest` y `manage.py check`, salvo que exista una razón documentada para una verificación más específica. Si cambiaste modelos, ejecuta también `makemigrations --check --dry-run`.
8. Si un test falla, analiza la causa. Tras dos intentos de corrección sin resolverlo, detente y reporta la causa raíz.
9. Actualiza `docs/plan.md` con cambios, pendientes y evidencia real. No marques como completado algo que no se verificó en esta sesión.
10. No avances al siguiente paso sin autorización.

El comando `/paso` automatiza este flujo y `/verifica` revisa el diff antes del commit. Si algo difiere entre este archivo y un comando, aplica este archivo e informa.

## 5. Límite de archivos y Git

- Máximo 4 archivos de código, plantillas, tests o migraciones modificados o creados por paso, salvo excepción explícitamente aprobada. La actualización obligatoria de `docs/plan.md` no cuenta para ese límite.
- No edites migraciones ya aplicadas; crea una migración nueva.
- No borres archivos sin autorización.
- No leas ni escribas `.env` salvo que el usuario autorice expresamente una tarea que lo requiera. Nunca incluyas su contenido en respuestas, logs o diffs.
- No ejecutes `git push`. El usuario lo realiza manualmente.
- Entrega diffs mínimos y explica cualquier modificación de contrato o dato persistido.

## 6. Arquitectura y dominio

Estructura actual conocida: `apps/core`, `apps/agents`, `apps/providers`, `apps/engine`, `apps/checks`, `apps/api` y `apps/panel`.

Mantén las responsabilidades diferenciadas:

- Agente: identidad y configuración del ejecutor.
- Habilidad: capacidad e instrucciones especializadas, con entradas y salidas definidas.
- Herramienta: acción externa explícita, con permisos y validación. Los secretos viven en `Credencial` y se referencian con placeholders; el modelo nunca los recibe.
- Workflow: definición ordenada de pasos.
- Ejecución: evidencia persistida de lo que ocurrió, incluyendo modelo y consumo cuando estén disponibles.
- Proveedor/modelo: conexión y características del servicio de IA.
- API: entrada autenticada de sistemas externos (`apps/api`); no contiene lógica de negocio.
- Panel: interacción y presentación; no debe convertirse en el lugar donde reside toda la lógica de negocio.

La base de datos es la fuente de verdad del estado. La cola dispara trabajo, pero no sustituye la persistencia. Las salidas de modelos deben validarse antes de usarse o guardarse. Las reservas y actualizaciones de cuotas deben ser atómicas.

### Evolución modular

ARM debe poder incorporar aplicaciones o módulos orientados a diferentes proyectos y tareas. Por ello:

- No acoples el motor de ejecución a WordPress, SEO ni a un único caso de uso.
- Mantén las integraciones externas separadas de los proveedores LLM. `apps/providers` contiene hoy el adaptador de WordPress por razones históricas; no añadas allí nuevas integraciones funcionales.
- Las credenciales deben pertenecer a la integración correspondiente y, cuando se introduzca el modelo de proyectos, quedar aisladas por proyecto/espacio de trabajo.
- No implementes multitenencia, permisos por proyecto ni nuevos modelos transversales sin un paso aprobado y un diseño de migración.
- No supongas que todos los agentes o módulos comparten las mismas herramientas, datos o permisos.
- Conserva contratos estables entre módulos y documenta cambios incompatibles.

## 7. Reglas de negocio aprobadas

- RB-009: rechazar la encolación si excede la cuota diaria o el límite RPM del proveedor.
- RB-010: si `modo_ejecucion` de una habilidad es `manual`, pausar el flujo y generar una tarea para revisión.
- RB-011: ejecutar workflows en orden; el paso N no se encola hasta que el paso N-1 esté en estado `ok`.
- RB-013: cifrar `api_key` antes de guardarla en la base de datos.
- RB-014: el límite diario de tokens por proveedor es obligatorio.
- RB-017: el endpoint REST requiere autenticación mediante token.

El estado de implementación de cada regla está en `docs/requirements/business-rules.md`. No cambies reglas aprobadas sin señalar el impacto y solicitar autorización. Las reglas marcadas `[PROPUESTO]` que no aparecen arriba (por ejemplo RB-015 y RB-016) no están aprobadas: no las implementes sin un paso aprobado.

## 8. Sistema visual

La interfaz utiliza el sistema centralizado ARM Flow definido en `static/css/app.css`. No reemplaces sus tokens ni inventes una identidad visual nueva.

La fuente de verdad son los tokens y clases reales de `static/css/app.css`. Si `docs/estandares/diseno-ui.md` u otro documento muestran valores o nombres distintos, prevalece `app.css`: informa la discrepancia y no "corrijas" el código para igualar el documento.

Antes de crear una clase, busca una equivalente en `app.css`. No supongas nombres de clase: compruébalos en el archivo y en el catálogo `panel/design_system.html` (ruta `design-system/` del panel, Paso UX-0).

HTML semántico y accesible. Cero estilos inline y cero bloques `<style>` en plantillas.

La navegación sigue el patrón "Centro de Mando" (Paso UI-NOD-01). Conserva su estructura al añadir pantallas.

La especificación de diseño vive en `.opencode/skills/design-linear-nod/SKILL.md` y la de formularios en `.opencode/skills/form-ux/SKILL.md`. Si existiera un `docs/estandares/diseno-ui.md` en el repositorio, ignóralo: está desactualizado y sus tokens (índigo `#6366F1`, fondo `#F5F5F7`) no coinciden con `app.css`.

## 9. Definición de terminado

Un paso se considera terminado solo cuando:

- Cumple el criterio de aceptación acordado.
- Las pruebas pertinentes pasan y se informa su salida real.
- `manage.py check` no presenta problemas, cuando aplique.
- Las migraciones necesarias se generaron y aplicaron en el entorno de desarrollo, y `makemigrations --check --dry-run` no detecta cambios, cuando aplique.
- No se introdujeron secretos, dependencias o cambios fuera del alcance.
- `docs/plan.md` refleja el estado real y los pendientes, y se mantiene en UTF-8 legible.
- Se entrega un resumen breve de archivos modificados, pruebas y riesgos restantes.

## 10. Estado del proyecto

El estado vive en `docs/plan.md` (cabecera "Estado Actual" y sección de cada paso), con el historial de los primeros pasos en `docs/plan_historial.md` y el roadmap en `docs/requirements/roadmap.md`. No dupliques aquí hitos ni listas de pasos completados: se desactualizan. No deduzcas que un paso está completado únicamente porque aparezca descrito en una conversación o en una propuesta.

## 11. Dirección de producto: agente de propósito general

ARM evoluciona hacia un Centro de Mando de agentes que ejecutan tareas de distintos tipos, no solo de contenido. Estos principios guían cualquier función nueva. Describen la dirección; no autorizan implementar nada sin un paso aprobado.

1. **Transparencia:** cada ejecución debe poder mostrar qué hizo el agente, con qué herramienta, modelo, tokens y resultado. Reutiliza `Ejecucion`, `Artefacto` y `RegistroEjecucionMonitoreo` en lugar de crear registros paralelos.
2. **Coste visible y acotado:** el coste o consumo por tarea debe poder consultarse y limitarse (RB-015 y RB-016 están propuestas, no aprobadas).
3. **Confirmación humana en acciones con efecto externo:** extiende el mecanismo existente (`modo_ejecucion=manual`, aprobación y trazabilidad del aprobador) en lugar de duplicarlo.
4. **Secretos fuera del alcance del modelo:** las credenciales se resuelven en el servidor mediante placeholders; ningún prompt, log ni salida las contiene.
5. **Permisos decididos por el servidor:** el modelo propone, el servidor autoriza según agente, herramienta, usuario y proyecto (`docs/estandares/seguridad.md`, sección 6).
6. **Funciones como módulos:** una capacidad nueva se incorpora como habilidades y herramientas de un módulo propio, con contratos estables, sin acoplarla al núcleo.

Quedan fuera de alcance hasta tener un diseño aprobado por separado: ejecución de código generado por el modelo, control de navegador o equipo (computer-use) y sandboxes, automatización de cuentas personales o pagos, base vectorial y multitenencia. Las soluciones de sandbox habituales requieren Docker o WSL, hoy prohibidos en la sección 3.

Al proponer una función nueva, el plan debe indicar: qué habilidad o herramienta añade, qué permisos requiere, qué efecto externo produce, cómo se aprueba y cómo se limita el coste.

## 12. Skills de OpenCode

Las skills de `.opencode/skills/<nombre>/SKILL.md` se cargan **automáticamente** según el tipo de tarea. No esperes a que el usuario las mencione; cárgalas tú cuando el paso toque el área correspondiente. Si una skill contradice este archivo o `docs/estandares/`, aplica la precedencia de la sección 2 e informa de la contradicción; no sigas la skill.

### Mapa de skills por tipo de tarea

| Tipo de tarea | Skill a cargar |
|---|---|
| Templates, CSS, componentes UI, iconos, layout | `design-linear-nod` |
| Formularios, `forms.py`, validación de entrada, UX de campos | `form-ux` |
| Vistas, `views.py`, `urls.py`, `models.py`, tareas Huey, arquitectura | `django-architecture` |
| Queries del ORM, `select_related`, índices, transacciones, `F()` | `performance-database` |
| Llamadas a LLM, agentes, `Router`, prompts, conteo de tokens | `ai-llm-integration` |
| Autenticación, autorización, SSRF, cifrado, credenciales, `@login_required` | `backend-security` |
| Logging, `try/except`, manejo de errores, tareas Huey que fallan | `error-handling` |
| Tests, `tests/`, mocks, fixtures, `pytest` | `testing-pytest` |

Si una tarea toca varios tipos (ej. crear una vista nueva con su template y su test), carga todas las skills correspondientes. No cargues skills que no apliquen.