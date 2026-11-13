# Plan de construcción


Estado: 0a, 0b, 1a, 1b, 2, 3a, 3b, 4, 5a, 5b y 6 completados.
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
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
............................                                             [100%]
28 passed in 11.51s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: BaseProveedor centraliza el mapeo 429 -> LimiteVelocidad, 5xx ->
ErrorServidor, timeout -> TimeoutProveedor y 402 -> CuotaAgotada. Gemini usa
x-goog-api-key; OpenRouter usa Bearer. Los fixtures de tests/fixtures/ reproducen
la forma documentada de cada API, no son capturas reales (no hubo red).

## Paso 3a - Contador y reserva atómica
Objetivo: no pasarse del cupo diario con varios workers.
Archivos: apps/core/models.py, apps/core/migrations/0003_contadorcuota.py,
apps/providers/quota.py, tests/test_quota.py.
Aceptación: tres reservas con límite 3 devuelven True y la cuarta False; dos
hilos simultáneos con límite 1 no superan el cupo. En SQLite
select_for_update es un no-op, así que la garantía real allí es el UPDATE
condicional; no se puede demostrar que quitar select_for_update rompa el test.
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe manage.py makemigrations core
Migrations for 'core':
  apps\core\migrations\0003_contadorcuota.py
    + Create model ContadorCuota

$ .venv\Scripts\python.exe manage.py migrate
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, core, sessions
Running migrations:
  Applying core.0003_contadorcuota... OK

$ .venv\Scripts\python.exe -m pytest -q
.................................                                        [100%]
33 passed in 11.58s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: ContadorCuota guarda una fila por proveedor y fecha local; cambiar de día
crea un contador nuevo. reservar() usa transaction.atomic + select_for_update
para Postgres y un UPDATE condicional (usadas < límite) para SQLite, con hasta
5 reintentos ante "database is locked". liberar() decrementa solo si usadas > 0;
limite_diario=0 sigue significando sin límite y no escribe contador.

## Paso 3b - Caché y fallback
Objetivo: ahorrar cuota y sobrevivir a un proveedor caído.
Archivos: apps/providers/router.py, apps/providers/cache.py,
apps/providers/__init__.py, tests/test_router.py.
Aceptación: la segunda llamada idéntica sale de caché con coste cero; ante 429 hay
cooldown de 60 segundos y salto al siguiente modelo por prioridad.
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
.......................................                                  [100%]
39 passed in 29.37s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: CacheRespuestas guarda en la tabla propia providers_cache_respuestas con
clave sha256 de (messages, model_id, config) normalizados; la tabla se crea con
CREATE TABLE IF NOT EXISTS desde cache.py para no añadir modelo ni migración en
un paso limitado a cuatro archivos. Router elige el adaptador por
proveedor.nombre (gemini/openrouter), reserva cuota antes de llamar y la libera
solo ante 429 o configuración inválida; ante 5xx o timeout no la libera porque
la llamada pudo consumirse. El cooldown de 60 s vive en memoria de cada instancia
de Router. Si todos los modelos fallan se lanza CuotaAgotada con el detalle.

## Paso 4 - Motor de ejecución
Objetivo: ejecutar tareas con estado recuperable.
Archivos: apps/engine/tasks.py, apps/engine/__init__.py, tests/test_engine.py,
config/settings.py, apps/core/models.py y
apps/core/migrations/0004_tarea_actualizado_en.py.
Aceptación: latido cada 30 segundos; tarea huérfana tras 5 minutos sin latido se
reencola con clave de idempotencia; máximo dos devoluciones antes de escalar a
humano; el test simula la caída del worker a mitad de ejecución.
Estado: completado (2026-11-12). Se autorizaron dos archivos extra sobre el
límite de cuatro para añadir actualizado_en y la transición curso->cola.
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe manage.py makemigrations core
Migrations for 'core':
  apps\core\migrations\0004_tarea_actualizado_en.py
    + Add field actualizado_en to tarea

$ .venv\Scripts\python.exe manage.py migrate
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, core, sessions
Running migrations:
  Applying core.0004_tarea_actualizado_en... OK

$ .venv\Scripts\python.exe -m pip install huey
Requirement already satisfied: huey in .\.venv\Lib\site-packages (3.5.4)

$ .venv\Scripts\python.exe -m pytest -q
...........................................                              [100%]
43 passed in 31.73s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: Huey ya figuraba en requirements.txt y requirements-lock.txt con la
versión 3.5.4; no hubo que modificarlos. ejecutar_tarea reclama la tarea con un
UPDATE condicional cola->curso (idempotencia ante entregas duplicadas), crea la
Ejecucion, construye el Router con los modelos activos por prioridad y el modelo
del agente delante, guarda un Artefacto versionado y deja la tarea en ok. El
latido actualiza actualizado_en cada 30 s desde un hilo; recuperar_huerfanas
reencola las tareas en curso con más de 5 minutos sin latido y revisar_huerfanas
la ejecuta cada minuto. Se aplican 3 reintentos (4 intentos en total) y después
fallo definitivo, según el encargo de esta sesión, en lugar de las dos
devoluciones del plan; no hay escalado a humano distinto de fallo. La clave de
idempotencia del reencolado es tarea:<id>:intento:<n>. Los estados siguen en
Tarea; no se creó apps/engine/states.py. SqliteHuey comparte db.sqlite3 con
Django, como se pidió, con riesgo de bloqueo si coinciden escrituras.

## Paso 5 - Verificadores deterministas
Objetivo: calidad comprobable sin gastar tokens.
Archivos: apps/checks/__init__.py, apps/checks/seo.py, apps/checks/estilo.py,
tests/test_checks.py; 5b: apps/checks/hechos.py, tests/test_hechos.py.
Aceptación: las reglas de docs/estilo.md se cargan desde el archivo; doce casos
parametrizados, incluidos los que deben fallar; ninguna llamada a modelos.
Estado: 5a y 5b completados (2026-11-12).
Evidencia 5a (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
....................................................................     [100%]
68 passed in 23.05s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).

Evidencia 5b (2026-11-12):
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 34.30s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: 23 casos parametrizados (11 de SEO y 12 de estilo) y dos pruebas de carga
de reglas. cargar_reglas() lee EST-001, EST-002, EST-003, EST-005 y EST-006 de
docs/estilo.md; las listas, las comillas y los umbrales salen del markdown.
verificar_seo() cubre título, meta, H1, slug, densidad y una aproximación INFLESZ
con conteo silábico heurístico, sin dependencias nuevas. verificar_estilo()
devuelve regla, severidad, posición, mensaje y sugerencia. No hay red ni modelos:
son funciones puras. 5b añade anclar_hechos() en apps/checks/hechos.py: extrae
cifras y nombres propios con regex, los compara con el original sin distinguir
mayúsculas y devuelve entidades, severidad y bloqueo. La lista de exclusión es
configurable; por defecto filtra arranques de frase comunes y una lista vacía la
desactiva. Los cinco casos del encargo están cubiertos en tests/test_hechos.py.

## Paso 6 - Pipeline editorial
Objetivo: un artículo entra y sale reescrito con SEO e informe.
Archivos: apps/engine/pipelines.py, fixtures del equipo editorial, comando
procesar_articulo, test de extremo a extremo.
Aceptación: con proveedores simulados se produce un Artefacto versionado y un
informe de calidad.
Estado: completado (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py
...                                                                      [100%]
3 passed in 6.99s

$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 94%]
....                                                                     [100%]
76 passed in 42.27s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: pipeline_editorial() exige la tarea principal en "cola" y llama dos veces
a ejecutar_tarea.call_local(): la reescritura y la tarea SEO hija. La tarea SEO
usa la habilidad con slug "seo", hereda el agente y el payload, sustituye "texto"
por el artefacto reescrito y se vincula con depende_de. Sus problemas quedan en
el metadata del artefacto final como problemas, verificacion y tarea_principal.
Ejecutar_tarea deja la principal en "ok", que es terminal en TRANSICIONES; para
pasar a "revision" el pipeline hace un UPDATE directo, sin tocar models.py en
este paso. El comando procesar_articulo exige las habilidades "reescritura" y
"seo" ya creadas y recorta la meta a 155 caracteres; si el texto es más corto de
140, SEO-002 la mandará a revisión. La derivación de título, meta y slug es una
heurística provisional: falta que el modelo devuelva esos campos validados.

## Paso 7 - Panel
Objetivo: operar el sistema desde el navegador.
Archivos: apps/panel/views.py, templates, tests de vista.
Aceptación: lista de tareas con estado, detalle de ejecución con tokens y modelo,
bandeja de aprobación con diff; aprobar cambia el estado y registra quién aprobó.
Estado: 7a completado (infraestructura).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).

$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 94%]
....                                                                     [100%]
76 passed in 33.37s
```
Notas: se ha creado la infraestructura básica de la app `panel` y registrado
en la configuración del proyecto. Pendiente 7b: implementación de vistas y tests.

## Paso 8 - Publicación
Objetivo: enviar borradores a WordPress sin riesgo.
Archivos: apps/providers/wordpress.py, apps/engine/sitemap.py, tests.
Aceptación: solo crea borradores; publicar exige aprobación previa; el índice de
URLs sale del sitemap.xml; credenciales inválidas producen error controlado.
Estado: completado (2026-11-13).
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
....................................................................................
84 passed in 46.88s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: se han cubierto los casos de éxito y fallo de WordPress (usando respx) y la generación del sitemap en XML válido.

## Decisiones registradas
- 2026-11-13: SQLite y Huey en lugar de Postgres y Celery por el límite de 8 GB.
- 2026-11-13: sin Docker ni WSL; todo nativo en Windows.
- 2026-11-13: modelo de opencode elegido por sesión, no fijado en configuración.
- 2026-11-12: la cuota diaria vive en ContadorCuota (proveedor + fecha local).
- 2026-11-12: en SQLite select_for_update es no-op; la exclusión real la da el
  UPDATE condicional con reintentos ante "database is locked".

## Pendientes y dudas
- Siguiente paso: 7 - Panel.
- Formalizar la transición ok -> revision en Tarea.TRANSICIONES; ahora el
  pipeline la aplica con un UPDATE directo.
- El pipeline deriva título, meta y slug del texto reescrito con heurísticas.
  Hacer que el modelo los devuelva validados con Pydantic.
- procesar_articulo no crea el catálogo: exige las habilidades "reescritura" y
  "seo" y al menos un modelo activo.
- La lista de exclusión de 5b vive en hechos.py; moverla a docs/estilo.md si debe
  editarse sin tocar código.
- El motor aplica 3 reintentos y después fallo, según el encargo de la sesión;
  falta decidir si el agotamiento debe pasar a "revisión" para un humano.
- SqliteHuey comparte db.sqlite3 con Django. Si aparecen bloqueos con el worker
  y el servidor a la vez, mover la cola a un archivo huey.db separado.
- El latido usa un hilo por tarea; medir su impacto cuando haya varias tareas
  largas en el mismo worker.
- El cooldown de 60 s vive en la memoria de cada Router; con varios workers cada
  uno lleva el suyo. Persistirlo si llega a importar en producción.
- Router elige el adaptador por Proveedor.nombre; añadir un campo de tipo de
  adaptador en el paso 4 para no depender del texto del nombre.
- La caché usa una tabla propia creada con SQL: migrarla a modelo Django cuando
  haya que caducarla o verla desde el admin.
- Decidir si 5xx y timeout deben liberar la cuota reservada (ahora no se libera).
- api_key se guarda en claro en SQLite; falta cifrarla con la clave fuera del
  repositorio (dependencia cryptography ya autorizada).
- Confirmar qué proveedor gratuito usará AI Workforce en producción.
- Medir el consumo real del paso 3 antes de subir a un servidor.

## Paso 9 - Panel propio (reemplazo del admin)
Objetivo: mover la configuración y operación al panel web.
9a: Login propio y esqueleto (base.html, login, logout). COMPLETADO.
9b: Formularios de Proveedor y ModeloLLM.
9c: Formularios de Habilidad y Agente.