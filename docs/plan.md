# Plan de construcción


Estado: 0a completado (entorno y requisitos fijados); 0b pendiente.
Última actualización: 2026-11-13.

Regla de cierre: un paso se cierra con tests en verde, este archivo actualizado y
un commit. Prohibido avanzar con tests rojos.

## Paso 0 - Esqueleto
Objetivo: proyecto que arranca y tiene una prueba.
Archivos: requirements.txt, manage.py, config/settings.py, config/urls.py,
.env.example, .gitignore, pytest.ini, apps/core/views.py, tests/test_health.py.
Aceptación: /healthz devuelve JSON con estado ok; pytest pasa; runserver arranca.
Estado: completado (0a entorno y requisitos; 0b proyecto Django, /healthz y test).

## Paso 1 - Modelos de datos
Objetivo: esquema persistente del sistema.
Archivos: apps/core/models.py, apps/core/admin.py, migración inicial, tests.
Aceptación: se crean Proveedor, ModeloLLM, Agente, Habilidad, Tarea, Ejecucion y
Artefacto desde el shell; las transiciones de estado quedan registradas.
Estado: pendiente.

## Paso 2 - Adaptadores de proveedores
Objetivo: capa de IA intercambiable.
Archivos: apps/providers/base.py, gemini.py, openrouter.py, tests con fixtures.
Aceptación: 429, 5xx y timeout se mapean a excepciones propias; cero llamadas de
red en los tests; el uso de tokens se normaliza entre proveedores.
Estado: pendiente.

## Paso 3a - Contador y reserva atómica
Objetivo: no pasarse del cupo diario con varios workers.
Archivos: apps/providers/quota.py, tests de concurrencia.
Aceptación: dos hilos simultáneos no superan el límite; el test falla si se quita
el select_for_update.
Estado: pendiente.

## Paso 3b - Caché y fallback
Objetivo: ahorrar cuota y sobrevivir a un proveedor caído.
Archivos: apps/providers/router.py, apps/providers/cache.py, tests.
Aceptación: la segunda llamada idéntica sale de caché con coste cero; ante 429 hay
cooldown de 60 segundos y salto al siguiente modelo por prioridad.
Estado: pendiente.

## Paso 4 - Motor de ejecución
Objetivo: ejecutar tareas con estado recuperable.
Archivos: apps/engine/tasks.py, apps/engine/states.py, tests.
Aceptación: latido cada 30 segundos; tarea huérfana tras 5 minutos sin latido se
reencola con clave de idempotencia; máximo dos devoluciones antes de escalar a
humano; el test simula la caída del worker a mitad de ejecución.
Estado: pendiente.

## Paso 5 - Verificadores deterministas
Objetivo: calidad comprobable sin gastar tokens.
Archivos: apps/checks/seo.py, apps/checks/estilo.py, apps/checks/hechos.py, tests.
Aceptación: las reglas de docs/estilo.md se cargan desde el archivo; doce casos
parametrizados, incluidos los que deben fallar; ninguna llamada a modelos.
Estado: pendiente.

## Paso 6 - Pipeline editorial
Objetivo: un artículo entra y sale reescrito con SEO e informe.
Archivos: apps/engine/pipelines.py, fixtures del equipo editorial, comando
procesar_articulo, test de extremo a extremo.
Aceptación: con proveedores simulados se produce un Artefacto versionado y un
informe de calidad.
Estado: pendiente.

## Paso 7 - Panel
Objetivo: operar el sistema desde el navegador.
Archivos: apps/panel/views.py, templates, tests de vista.
Aceptación: lista de tareas con estado, detalle de ejecución con tokens y modelo,
bandeja de aprobación con diff; aprobar cambia el estado y registra quién aprobó.
Estado: pendiente.

## Paso 8 - Publicación
Objetivo: enviar borradores a WordPress sin riesgo.
Archivos: apps/providers/wordpress.py, apps/engine/sitemap.py, tests.
Aceptación: solo crea borradores; publicar exige aprobación previa; el índice de
URLs sale del sitemap.xml; credenciales inválidas producen error controlado.
Estado: pendiente.

## Decisiones registradas
- 2026-11-13: SQLite y Huey en lugar de Postgres y Celery por el límite de 8 GB.
- 2026-11-13: sin Docker ni WSL; todo nativo en Windows.
- 2026-11-13: modelo de opencode elegido por sesión, no fijado en configuración.

## Pendientes y dudas
- Confirmar qué proveedor gratuito usará AI Workforce en producción.
- Medir el consumo real del paso 3 antes de subir a un servidor.