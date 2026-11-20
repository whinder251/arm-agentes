# ARM — Instrucciones generales para agentes de desarrollo

ARM es una plataforma modular de orquestación y ejecución de tareas mediante agentes de IA. El módulo actual está orientado a workflows y publicación de contenido, pero la arquitectura debe permitir incorporar otros módulos y casos de uso sin convertir el núcleo en una aplicación dependiente de SEO o WordPress.

## 1. Principios de trabajo

1. Conserva la arquitectura, convenciones y comportamiento existentes. Inspecciona el código relacionado antes de proponer cambios.
2. No reconstruyas componentes que ya existen. Busca primero modelos, servicios, utilidades, formularios, componentes UI y pruebas reutilizables.
3. Implementa el cambio mínimo que resuelva el requisito, sin sacrificar seguridad, integridad, legibilidad ni pruebas.
4. No inventes APIs, firmas, parámetros ni capacidades de dependencias. Comprueba la documentación o declara la incertidumbre.
5. No añadas dependencias sin justificar el problema, alternativas, impacto de mantenimiento y solicitar aprobación.
6. No hagas refactors amplios dentro de una tarea funcional pequeña.
7. No ocultes fallos con excepciones genéricas, valores por defecto silenciosos o estados de éxito falsos.
8. No afirmes que una prueba, comando, migración o verificación se ejecutó si no se ejecutó en esta sesión.

## 2. Documentación obligatoria

Consulta los estándares que correspondan al cambio:

- `docs/estandares/codigo.md`: Python, Django, modelos, servicios, consultas, workers, API y arquitectura.
- `docs/estandares/seguridad.md`: autenticación, autorización, credenciales, integraciones, archivos, agentes y despliegue.
- `docs/estandares/diseno-ui.md`: plantillas, CSS, JavaScript, componentes y experiencia de usuario.
- `docs/estandares/pruebas.md`: pruebas nuevas, cambios de comportamiento, regresión y verificación.

`docs/estilo.md` es exclusivamente el conjunto de reglas para evaluar el contenido producido por los agentes (artículos, titulares y metadatos). No es el estándar de código ni la guía visual del panel.

Si un cambio afecta varias áreas, consulta todos los estándares pertinentes. Si una regla parece contradecir el código actual o una decisión aprobada, no la resuelvas por intuición: informa del conflicto y propone una decisión.

## 3. Entorno y restricciones actuales

- Desarrollo local actual: Windows 11, PowerShell 5.1 y Python 3.12 dentro de `.venv`.
- Base de datos de desarrollo actual: SQLite en modo WAL.
- Cola actual: Huey con SqliteHuey.
- No introducir Docker, WSL, Redis, Celery, Celery Beat, Node, npm, LangChain o CrewAI en esta etapa.
- Dependencias autorizadas actuales: Django 5.2 LTS, Huey, httpx, Pydantic v2, python-dotenv, cryptography, pytest, pytest-django y respx.
- Una dependencia adicional requiere justificación y aprobación explícita.
- Las restricciones anteriores describen el entorno y la etapa actuales; no significan que ARM deba quedar limitado a SQLite en producción. La preparación para PostgreSQL y otros componentes de producción debe hacerse mediante un paso aprobado y documentado.

### Comandos PowerShell

Usa el intérprete del entorno virtual:

- Servidor: `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000`
- Worker: `.venv\Scripts\python.exe manage.py run_huey`
- Tests: `.venv\Scripts\python.exe -m pytest -q`
- Comprobación: `.venv\Scripts\python.exe manage.py check`
- Migraciones: `.venv\Scripts\python.exe manage.py makemigrations`
- Aplicar migraciones: `.venv\Scripts\python.exe manage.py migrate`

No uses `&&`; ejecuta comandos PowerShell en líneas separadas. Cita rutas que contengan espacios. No uses `Get-Content` para leer archivos si está disponible una herramienta de lectura adecuada.

## 4. Flujo obligatorio de implementación

1. Trabaja en un solo paso solicitado por vez.
2. Antes de escribir código, lee este archivo, el apartado pertinente de `docs/plan.md` y los estándares aplicables.
3. Presenta un plan de menos de 10 líneas con archivos previstos (máximo 4 por cambio, salvo excepción aprobada), riesgos y criterios de aceptación.
4. Espera aprobación explícita antes de implementar.
5. Escribe o actualiza pruebas antes o junto con el código.
6. Los tests no deben llamar servicios externos reales. Usa `respx` y fixtures cuando corresponda.
7. Ejecuta las verificaciones pertinentes. Como mínimo, antes de cerrar un cambio de código ejecuta `pytest` y `manage.py check`, salvo que exista una razón documentada para una verificación más específica.
8. Si un test falla, analiza la causa. Tras dos intentos de corrección sin resolverlo, detente y reporta la causa raíz.
9. Actualiza `docs/plan.md` con cambios, pendientes y evidencia real. No marques como completado algo que no se verificó en esta sesión.
10. No avances al siguiente paso sin autorización.

## 5. Límite de archivos y Git

- Máximo 4 archivos modificados o creados por paso, salvo excepción explícitamente aprobada.
- No edites migraciones ya aplicadas; crea una migración nueva.
- No borres archivos sin autorización.
- No leas ni escribas `.env` salvo que el usuario autorice expresamente una tarea que lo requiera. Nunca incluyas su contenido en respuestas, logs o diffs.
- No ejecutes `git push`. El usuario lo realiza manualmente.
- Entrega diffs mínimos y explica cualquier modificación de contrato o dato persistido.

## 6. Arquitectura y dominio

Estructura actual conocida: `apps/core`, `apps/agents`, `apps/providers`, `apps/engine`, `apps/checks` y `apps/panel`.

Mantén las responsabilidades diferenciadas:

- Agente: identidad y configuración del ejecutor.
- Habilidad: capacidad e instrucciones especializadas, con entradas y salidas definidas.
- Herramienta: acción externa explícita, con permisos y validación.
- Workflow: definición ordenada de pasos.
- Ejecución: evidencia persistida de lo que ocurrió, incluyendo modelo y consumo cuando estén disponibles.
- Proveedor/modelo: conexión y características del servicio de IA.
- Panel: interacción y presentación; no debe convertirse en el lugar donde reside toda la lógica de negocio.

La base de datos es la fuente de verdad del estado. La cola dispara trabajo, pero no sustituye la persistencia. Las salidas de modelos deben validarse antes de usarse o guardarse. Las reservas y actualizaciones de cuotas deben ser atómicas.

### Evolución modular

ARM debe poder incorporar aplicaciones o módulos orientados a diferentes proyectos y tareas. Por ello:

- No acoples el motor de ejecución a WordPress, SEO ni a un único caso de uso.
- Mantén las integraciones externas separadas de los proveedores LLM.
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

No cambies reglas aprobadas sin señalar el impacto y solicitar autorización.

## 8. Sistema visual

La interfaz existente utiliza el sistema centralizado ARM Flow definido en `static/css/app.css`. No reemplaces sus tokens ni inventes una identidad visual nueva. La especificación completa está en `docs/estandares/diseno-ui.md`.

## 9. Definición de terminado

Un paso se considera terminado solo cuando:

- Cumple el criterio de aceptación acordado.
- Las pruebas pertinentes pasan y se informa su salida real.
- `manage.py check` no presenta problemas, cuando aplique.
- Las migraciones necesarias se generaron y aplicaron en el entorno de desarrollo, cuando aplique.
- No se introdujeron secretos, dependencias o cambios fuera del alcance.
- `docs/plan.md` refleja el estado real y los pendientes.
- Se entrega un resumen breve de archivos modificados, pruebas y riesgos restantes.

## 10. Estado del proyecto

Consulta `docs/plan.md` y `docs/requirements/roadmap.md` para conocer el avance. No deduzcas que un paso está completado únicamente porque aparezca descrito en una conversación o en una propuesta.

### Hitos recientes completados

- SEARCH-FIX-01: Búsqueda Web con metadatos directos. Los resultados de DuckDuckGo (titulo, resumen, URL y fecha) se registran directamente como Hallazgo en modo busqueda, sin pasar por extraccion de enlaces internos.
- RETRY-CONTENT-01: Reintentos automaticos de extraccion de contenido. Si un hallazgo existe pero contenido_extraido esta vacio, el sistema vuelve a intentar la extraccion.
- SCHEDULE-FIX-01: Correccion del desplazamiento horario en programaciones. ultima_ejecucion guarda la hora de inicio, no la de fin, evitando desplazamientos acumulativos (10:00, 11:00, 12:00...).
- PUENTE-02: Flujo funcional Hallazgo -> Tarea con idempotencia por hallazgo_id, payload con clave texto, validacion estricta de habilidad y encolado real en Huey.
- HYGIENE-01 y UI-FIX-01: Limpieza de repositorio y correcciones de UI (etiqueta de columna de tiempo en historial de ejecuciones).

El motor de monitoreo soporta multiples fuentes por investigacion, limite de articulos por fuente, historial de ejecuciones con trazabilidad (RegistroEjecucionMonitoreo), y correccion de horarios.
