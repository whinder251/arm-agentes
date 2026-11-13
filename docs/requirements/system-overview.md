# ARM — Visión General del Sistema

## Propósito
ARM (Agent Resource Management) es un orquestador de agentes de IA que automatiza la transformación, verificación y publicación de contenido. Recibe texto, lo procesa mediante habilidades ejecutadas por modelos externos, valida el resultado con comprobadores deterministas y lo deja listo para publicación con aprobación humana en los puntos sensibles.

## Alcance
- Procesamiento de contenido mediante agentes de IA con habilidades específicas
- Validación automática de calidad (estilo, hechos, SEO)
- Aprobación humana para acciones sensibles
- Publicación en WordPress vía API REST
- Integración con sistemas externos vía webhook
- Gestión de cuotas y presupuestos de uso de IA

## Usuarios
- Administrador: configura proveedores, modelos, habilidades, agentes y equipos
- Editor: crea tareas, revisa resultados, aprueba publicaciones
- Visor (futuro): consulta estado de tareas y flujos

## Contexto Operativo
- Windows 11, Python 3.12, Django 5.2 LTS
- SQLite en modo WAL (desarrollo), PostgreSQL (producción)
- Huey para cola de tareas con SqliteHuey
- Sin Docker, sin WSL, sin Redis, sin Celery

## Arquitectura de Alto Nivel
- apps/core: modelos de datos (Tarea, Agente, Habilidad, Proveedor, ModeloLLM, Workflow, Equipo)
- apps/agents: lógica de agentes y equipos
- apps/engine: motor de ejecución, pipeline, orquestador
- apps/checks: verificadores deterministas (estilo, hechos, SEO)
- apps/providers: integraciones externas (WordPress, APIs de IA)
- apps/panel: interfaz web de administración