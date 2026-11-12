# Plan de construcción


Estado: 0a, 0b, 1a y 1b completados; paso 2 pendiente.
Última actualización: 2026-11-12.

Regla de cierre: un paso se cierra con tests en verde, este archivo actualizado y
un commit. Prohibido avanzar con tests rojos.

## Paso 0 - Esqueleto
Objetivo: proyecto que arranca y tiene una prueba.
Archivos: requirements.txt, manage.py, config/settings.py, config/urls.py,
.env.example, .gitignore, pytest.ini, apps/core/views.py, tests/test_health.py.
Aceptación: /healthz devuelve JSON con estado ok; pytest pasa; runserver arranca.
Estado: completado (0a entorno y requisitos; 0b proyecto Django, /healthz y test).
Evidencia (2026-11-12):
- .venv\Scripts\python.exe -m pytest -q -> 1 passed in 0.22s
- .venv\Scripts\python.exe manage.py check -> System check identified no issues (0 silenced).

## Paso 1a - Modelos de catálogo
Objetivo: catálogo persistente de proveedores, modelos, habilidades y agentes.
Archivos: apps/core/models.py, apps/core/admin.py, tests/test_models.py,
apps/core/migrations/0001_initial.py.
Aceptación: los cuatro modelos se crean y se relacionan (FK y M2M), el slug de
Habilidad es único, admin registrado con list_display útil.
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe manage.py makemigrations core
Migrations for 'core':
  apps\core\migrations\0001_initial.py
    + Create model Habilidad
    + Create model ModeloLLM
    + Create model Proveedor
    + Create model Agente
    + Add field proveedor to modelollm
    + Create constraint unique_modelo_por_proveedor on model modelollm

$ .venv\Scripts\python.exe manage.py migrate
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, core, sessions
Running migrations:
  Applying core.0001_initial... OK

$ .venv\Scripts\python.exe -m pytest -q
........                                                                 [100%]
8 passed in 1.95s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```

## Paso 1b - Modelos de trabajo
Objetivo: esquema de tareas, ejecuciones y artefactos con transiciones de estado.
Archivos: apps/core/models.py, apps/core/admin.py, migración nueva, tests.
Aceptación: se crean Tarea, Ejecucion y Artefacto; las transiciones de estado
quedan registradas.
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe manage.py makemigrations core
Migrations for 'core':
  apps\core\migrations\0002_tarea_ejecucion_artefacto.py
    + Create model Tarea
    + Create model Ejecucion
    + Create model Artefacto

$ .venv\Scripts\python.exe manage.py migrate
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, core, sessions
Running migrations:
  Applying core.0002_tarea_ejecucion_artefacto... OK

$ .venv\Scripts\python.exe -m pytest -q
...............                                                          [100%]
15 passed in 1.19s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: las transiciones válidas viven en Tarea.TRANSICIONES y se aplican con
transicionar(); "fallo" es terminal en este paso. La reintención fallo->cola se
definirá con el motor (paso 4).

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
- Siguiente paso: 2 - Adaptadores de proveedores.
- Definir en el paso 4 la reintención fallo->cola y el límite de intentos.
- api_key se guarda en claro en SQLite; falta cifrarla con la clave fuera del
  repositorio (dependencia cryptography ya autorizada).
- Confirmar qué proveedor gratuito usará AI Workforce en producción.
- Medir el consumo real del paso 3 antes de subir a un servidor.