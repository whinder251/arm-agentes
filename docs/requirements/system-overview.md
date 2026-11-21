> **Nota**: Este documento describe el estado del proyecto en noviembre 2026 (pasos 0-23). Para el estado actual, consulta docs/plan.md.

# ARM â€” VisiÃ³n General del Sistema

## PropÃ³sito
ARM (Agent Resource Management) es un orquestador de agentes de IA que automatiza la transformaciÃ³n, verificaciÃ³n y publicaciÃ³n de contenido. Recibe texto, lo procesa mediante habilidades ejecutadas por modelos externos, valida el resultado con comprobadores deterministas y lo deja listo para publicaciÃ³n con aprobaciÃ³n humana en los puntos sensibles.

## Alcance
- Procesamiento de contenido mediante agentes de IA con habilidades especÃ­ficas
- ValidaciÃ³n automÃ¡tica de calidad (estilo, hechos, SEO)
- AprobaciÃ³n humana para acciones sensibles
- PublicaciÃ³n en WordPress vÃ­a API REST
- IntegraciÃ³n con sistemas externos vÃ­a webhook
- GestiÃ³n de cuotas y presupuestos de uso de IA

## Usuarios
- Administrador: configura proveedores, modelos, habilidades, agentes y equipos
- Editor: crea tareas, revisa resultados, aprueba publicaciones
- Visor (futuro): consulta estado de tareas y flujos

## Contexto Operativo
- Windows 11, Python 3.12, Django 5.2 LTS
- SQLite en modo WAL (desarrollo), PostgreSQL (producciÃ³n)
- Huey para cola de tareas con SqliteHuey
- Sin Docker, sin WSL, sin Redis, sin Celery

## Arquitectura de Alto Nivel
- apps/core: modelos de datos (Tarea, Agente, Habilidad, Proveedor, ModeloLLM, Workflow, Equipo)
- apps/agents: lÃ³gica de agentes y equipos
- apps/engine: motor de ejecuciÃ³n, pipeline, orquestador
- apps/checks: verificadores deterministas (estilo, hechos, SEO)
- apps/providers: integraciones externas (WordPress, APIs de IA)
- apps/panel: interfaz web de administraciÃ³n
