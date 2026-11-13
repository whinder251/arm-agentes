# Plan de construcción


Estado: 0a, 0b, 1a, 1b, 2, 3a, 3b, 4, 5a, 5b, 6, 9a, 9b, 9c, 9d-1, 9d-2, 9e,
10a, 10b, 11a, 11b, 12, 13 y 14 completados.
Pasos 9 (panel propio), 11 (rediseño visual), 12 (creación flexible de tareas),
13 (encolado en Huey desde el panel) y 14 (interfaz tipo chat, asignación
automática y borrado de tareas) completos.
Última actualización: 2026-11-13.

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
- Panel propio (paso 9) y rediseño visual (paso 11) cerrados. Queda revisar el
  resultado en navegador y el comportamiento responsive de las columnas.
- Validar que el JSON de esquema_salida sea un objeto antes de guardarlo desde
  HabilidadForm.
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
9b: Formularios de Proveedor y ModeloLLM. COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
90 passed, 1 warning in 98.68s

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: la advertencia es RemovedInDjango60Warning de URLField (preexistente, no es error de check). Se añadieron apps/panel/forms.py, apps/panel/views.py (vistas configuracion, crear_proveedor, crear_modelo con @login_required), apps/panel/templates/panel/configuracion.html (layout 60/40, tarjetas y fichas, paleta estricta, formularios en bloques condicionales), apps/panel/urls.py (rutas nuevas, autorizado como 5º archivo) y tests/test_panel_config.py (sin login 302, crear proveedor 302+DB, crear modelo 302+DB).
9c: Formularios de Habilidad y Agente. COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 76%]
......................                                                   [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
94 passed, 1 warning in 100.84s (0:01:40)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: se añadieron HabilidadForm y AgenteForm en apps/panel/forms.py;
crear_habilidad y crear_agente en apps/panel/views.py con @login_required;
agente_form.html con layout 60/40, plantillas de personalidad (Redactor SEO,
Analista, Asistente), textarea monoespaciado, slider de temperatura 0-2 con
track #009CFF, tarjetas de modelo con radio oculto y grilla de habilidades con
checkbox oculto y borde izquierdo de 4px #009CFF al marcar (selector :has con
respaldo por clase `.seleccionada`); tests/test_panel_agente.py con 4 casos
(los 3 del encargo más una comprobación de que el formulario renderiza).
crear_agente lee request.POST.getlist('habilidades') y aplica
agente.habilidades.set(ids); solo lista modelos activos. Se registraron las
rutas en apps/panel/urls.py (5º archivo) y se añadieron los botones "Añadir
Habilidad" y "Añadir Agente" en configuracion.html (6º archivo).
Desviación informada: para que el botón "Añadir Habilidad" no quedara muerto se
añadió en configuracion.html un bloque condicional con {{ form_habilidad.as_p }},
además de los botones autorizados; retirar si se prefiere otra ubicación.
La advertencia RemovedInDjango60Warning de URLField es preexistente.
Pendiente: 9d-2 (listado, edición y borrado de agentes, y enlaces del sidebar;
ahora apuntan a "#") y validar que el JSON de esquema_salida sea un objeto.
El listado, la edición y el borrado de habilidades quedaron resueltos en 9d-1.

9d-1: Listado, edición y eliminación de Habilidades. COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 71%]
.............................                                            [100%]
101 passed, 1 warning in 148.08s (0:02:28)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: se añadieron lista_habilidades, editar_habilidad y eliminar_habilidad en
apps/panel/views.py con @login_required. eliminar_habilidad lleva @require_POST:
un GET devuelve 405 y no borra; el POST redirige a la lista tras eliminar. Las
rutas se registraron en apps/panel/urls.py (configuracion/habilidades/,
.../<pk>/editar/ y .../<pk>/eliminar/). lista_habilidades.html muestra una tabla
con Nombre, Slug y acciones; el botón de borrado es un formulario POST con
csrf_token, fondo #c1121f y sin sombras ni radios. editar_habilidad reutiliza la
misma plantilla con HabilidadForm y muestra errores por campo. Tests nuevos en
tests/test_panel_listas.py: 7 casos (lista sin login 302, lista 200, formulario
200, edición 302 con datos persistidos, borrado POST 302, GET 405 sin borrar y
POST sin login 302). La advertencia RemovedInDjango60Warning de URLField sigue
siendo preexistente. No se tocó base.html: el enlace del sidebar de Habilidades
queda para 9d-2 junto con los de Agentes.

9d-2: Listado, edición y eliminación de Agentes, y corrección del sidebar.
COMPLETADO (2026-11-12). Paso 9 completo.
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 67%]
...................................                                      [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
107 passed, 1 warning in 163.65s (0:02:43)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: se añadieron lista_agentes, editar_agente y eliminar_agente en
apps/panel/views.py con @login_required; eliminar_agente lleva además
@require_POST, de modo que un GET devuelve 405 y no borra. Las rutas se
registraron en apps/panel/urls.py (configuracion/agentes/,
.../<pk>/editar/ y .../<pk>/eliminar/). lista_agentes.html muestra una tabla con
Nombre, Modelo asignado y acciones; el botón de borrado es un formulario POST con
csrf_token y fondo #c1121f. editar_agente reutiliza AgenteForm, lee
request.POST.getlist("habilidades") y aplica agente.habilidades.set(ids); en el
GET preselecciona las habilidades actuales del agente. base.html enlaza el
sidebar con {% url 'lista_habilidades' %} y {% url 'lista_agentes' %}. Tests
nuevos en tests/test_panel_listas.py: 6 casos de agentes (lista sin login 302,
lista 200 con modelo, formulario 200 con habilidad marcada, edición 302 con
datos y habilidades persistidos, borrado POST 302 y GET 405 sin borrar). La
advertencia RemovedInDjango60Warning de URLField sigue siendo preexistente.

9e: Migración de tareas.html al diseño nuevo y enlaces del menú.
COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 66%]
.....................................                                    [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
109 passed, 1 warning in 136.13s (0:02:16)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: tareas.html ahora extiende panel/base.html y solo define el bloque
content, con filtros por estado, tabla y vista de detalle condicional (payload,
último artefacto y última ejecución). Se eliminaron html, head, style global y
body. Los badges usan cola #5a5a5a, curso #009CFF, revision #fd7e14, ok #2e7d32
y fallo #c1121f, sin sombras rgba ni radios. fila_tarea.html es un parcial puro
con el <tr> y el botón Aprobar; se reutiliza en el bucle y es lo que devuelve
aprobar_tarea cuando HX-Request está presente. El botón envía X-CSRFToken por
hx-headers, que antes faltaba. base.html carga HTMX en el head (antes vivía en
tareas.html) y enlaza Proveedores y Modelos con {% url 'configuracion' %}.
Tests nuevos en tests/test_panel.py: respuesta HTMX sin <html> ni sidebar y
estado ok, y sidebar con dos enlaces a configuración y sin href="#".
Pendiente: el filtro por estado y la tabla no se refrescan por HTMX; el parcial
solo cubre la aprobación de una fila. La advertencia RemovedInDjango60Warning de
URLField sigue siendo preexistente. 

## Paso 10 - Mejoras de usabilidad del panel
Objetivo: facilitar la creación de tareas y la edición de agentes desde la interfaz web.
10a: Arreglar formulario de edición de agentes (renderizado de modelos como tarjetas).
COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 66%]
.....................................                                    [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
109 passed, 1 warning in 134.14s (0:02:14)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: la causa raíz estaba en AgenteForm.__init__; el RadioSelect nuevo se
creaba sin choices y form.modelo iteraba vacío. Ahora recibe las choices del campo
(tercer archivo autorizado en la sesión). lista_agentes.html separa "modelo" del
bucle genérico y lo pinta con .modelo-card (radio oculto, borde #D2D2D7, selección
#0071E3 y radius 12px, según el sistema Apple vigente); el bloque {% else %} no se
tocó. tests/test_panel_listas.py comprueba la tarjeta y el modelo actual marcado.
La advertencia RemovedInDjango60Warning de URLField es preexistente. El arreglo de
forms.py también hace visible la lista de modelos en agente_form.html.
10b: Creación de tareas desde el panel con asignación automática de agente (formulario de texto + keyword).
COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 64%]
........................................                                 [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
112 passed, 1 warning in 139.58s (0:02:19)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: crear_tarea en apps/panel/views.py (con @login_required) valida texto y
keyword obligatorios y busca el agente en una sola consulta con
annotate(Count("habilidades", filter=Q(...))) y coincidencias == 2, porque
habilidades__slug__in por sí solo es un OR y no garantiza ambas habilidades. La
tarea se crea en estado cola con el agente encontrado y la Habilidad
"reescritura" (Tarea.habilidad es FK obligatoria y PROTECT); el payload guarda
texto, keyword e instrucciones si vienen. Sin agente válido renderiza la misma
plantilla con error en rojo #FF3B30 sin crear fila; con éxito redirige a
lista_tareas con messages.success, que tareas.html pinta en un aviso. La ruta es
tarea/nueva/ en apps/panel/urls.py, declarada antes de tarea/<int:pk>/. La
plantilla nueva crear_tarea.html aplica la paleta Apple (fondo #F5F5F7, tarjeta
blanca, radios 12/8 y foco #0071E3); base.html conserva la paleta antigua hasta
el paso 11. Tests nuevos en tests/test_panel.py: login requerido, creación
exitosa con tarea en cola y agente asignado, y error visible sin agente con
ambas habilidades. La advertencia RemovedInDjango60Warning de URLField sigue
siendo preexistente.
Pendiente: el formulario no dispara la ejecución de la tarea (solo la encola);
los slugs reescritura/seo están fijos en views.py; el listado no se refresca por
HTMX tras crear; el resto del panel conserva la paleta antigua hasta el paso 11.


## Paso 11 - Rediseño visual estilo Apple/SaaS
Objetivo: migrar todo el panel al nuevo sistema de diseño (fondo #F5F5F7, tarjetas blancas con sombras suaves, bordes redondeados, tipografía SF Pro, acento azul #0071E3).
Archivos: base.html, tareas.html, lista_agentes.html, lista_habilidades.html, configuracion.html, agente_form.html, crear_tarea.html, fila_tarea.html.
Criterio: todas las vistas del panel respetan la paleta, tipografía, radios y sombras del nuevo sistema.

11a: Núcleo del panel (base, listado y detalle de tareas). COMPLETADO (2026-11-12).
Evidencia (2026-11-12):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 64%]
........................................                                 [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
112 passed, 1 warning in 163.23s (0:02:43)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: base.html pasa a fondo #F5F5F7, texto #1D1D1F y tipografía del sistema
(-apple-system/SF Pro); sidebar de 260px con rgba(255,255,255,0.8),
backdrop-filter blur(20px), borde #D2D2D7 y enlaces con hover #0071E3. Botones e
inputs usan radios de 8px, sombra suave y foco azul; el botón de logout pasa de
#c1121f a #FF3B30. tareas.html elimina los tonos crema: tabla con solo líneas
horizontales #D2D2D7, header #F5F5F7 con texto #6E6E73 y weight 600, badges de
12px con los colores pedidos y fondo al 10%, filtros tipo pill sin subrayado y
tarjetas de detalle con radio 12px y sombra suave. No existe
detalle_tarea.html: el detalle vive en tareas.html y se restilizó allí.
fila_tarea.html solo añade type="button"; el estilo del botón Aprobar (#0071E3,
hover con sombra) vive en tareas.html y el <tr id="task-N"> se mantiene intacto
para HTMX. Los 112 tests y el check pasan; la advertencia de URLField es
preexistente.

11b: Listas, configuración y formularios. COMPLETADO (2026-11-13).
Paso 11 completo.
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 64%]
........................................                                 [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
112 passed, 1 warning in 143.53s (0:02:23)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: lista_habilidades.html y lista_agentes.html migran sus tablas a
border-collapse separate con fondo #FFFFFF, borde #D2D2D7, radio 12px, sombra
suave y overflow hidden; el header usa #F5F5F7, texto #6E6E73, weight 600 y
mayúsculas, y las filas solo llevan línea inferior #D2D2D7. Los botones pasan a
#0071E3 (hover #0062c4) y los de eliminar a #FF3B30, ambos con radio 8px. Los
formularios de edición son tarjetas blancas de radio 12px y sus inputs y
textareas usan borde #D2D2D7, radio 8px y foco #0071E3 sin outline.
configuracion.html aplica el mismo sistema a tarjetas, fichas, secciones de
formulario y barra de acciones; los estados activo/inactivo pasan de estilos
inline a badges de radio 12px, padding 4px 10px y 0.75rem; los botones Cancelar
quedan como secundarios con borde #D2D2D7 (solo Eliminar es destructivo) y se
eliminan los style inline. agente_form.html actualiza las tarjetas de modelo y
habilidad: borde izquierdo #0071E3 y fondo #F5F5F7 al seleccionar, radio 12px;
el textarea pasa a fondo blanco, el slider a track #0071E3 con thumb circular
blanco y el botón Cancelar a secundario. No se tocaron views.py ni urls.py y toda
la lógica de plantillas (csrf, bucles, condicionales y forms) queda intacta. No
se añadieron tests: el cambio es solo CSS y las pruebas de render existentes
cubren las cuatro vistas; se verificó por búsqueda que no quedan #faf5e5,
#d5ceb9, #5a5a5a, #009CFF, #c1121f ni estilos inline en estos archivos. La
advertencia RemovedInDjango60Warning de URLField sigue siendo preexistente.
Pendiente: revisar el resultado en navegador y el responsive de las columnas
60/40 y 3/2 en pantallas estrechas.


## Paso 12 - Flexibilidad en creación de tareas
Objetivo: permitir selección manual de agente y hacer la keyword opcional.
12a: Modificar vista crear_tarea para aceptar agente_id y keyword opcional.
12b: Actualizar formulario con selector de agentes y ajustar tests.
Estado: completado (2026-11-13).
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 63%]
.........................................                                [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
113 passed, 1 warning in 151.45s (0:02:31)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: crear_tarea ya no busca agentes por habilidades. El POST exige agente_id,
lo valida contra Agente y renderiza "Debes seleccionar un agente" si falta; si
el agente tiene modelo inactivo devuelve "El agente seleccionado no está activo".
Agente no tiene campo activo propio, así que la actividad se comprueba en su
ModeloLLM. La keyword es opcional: si viene vacía no se añade al payload. Se
mantiene la FK obligatoria Tarea.habilidad con el slug "reescritura". El
formulario incorpora un select con todos los agentes ("Nombre (Modelo:
model_id)") con borde #D2D2D7, radio 8px y foco #0071E3. Tests: se ajustó
test_crear_tarea_exitoso para enviar agente_id, se renombró el caso sin agente a
test_crear_tarea_sin_agente_seleccionado y se añadió
test_crear_tarea_sin_keyword, que verifica que el payload no contiene esa clave.
La advertencia RemovedInDjango60Warning de URLField sigue siendo preexistente.
Pendiente: los agentes sin modelo o con modelo inactivo no se filtran en el
select. El encolado en Huey quedó resuelto en el paso 13.


## Paso 13 - Encolar tarea en Huey al crearla desde el panel
Objetivo: que la vista crear_tarea encole la tarea en Huey tras crear la fila,
para que el worker la procese.
Archivos: apps/panel/views.py (import y encolado), tests/test_panel.py (mock de
la llamada).
Criterio: el POST válido crea la tarea y encola una vez con su pk; los casos
inválidos no encolan; tests verifican la llamada con mock.
Estado: completado (2026-11-13).
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 63%]
.........................................                                [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
113 passed, 1 warning in 167.74s (0:02:47)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: `@db_task()` de Huey devuelve un `huey.api.TaskWrapper`, que no expone
`.delay`; la forma correcta de encolar es invocar el wrapper con
`ejecutar_tarea(tarea.pk)`. El import está al inicio de views.py y la llamada va
justo después del `Tarea.objects.create(...)`. Los tests parchean
`apps.panel.views.ejecutar_tarea`: el caso exitoso y el de sin keyword usan
`assert_called_once_with(tarea.pk)`, y el de sin agente usa `assert_not_called()`
sin crear fila. La advertencia RemovedInDjango60Warning de URLField es
preexistente.
Pendiente: validar con el worker real (`run_huey`) que la tarea pasa de cola a
ok o revisión; los tests mockean el encolado y no ejecutan Huey.

## Paso 14 - Interfaz tipo Chat, asignación inteligente y eliminación de tareas
Objetivo: simplificar la creación de tareas a un diseño tipo chat, asignar agente automáticamente si no se elige, y añadir botón para eliminar tareas.
Archivos: apps/panel/views.py, apps/panel/urls.py, apps/panel/templates/panel/crear_tarea.html, apps/panel/templates/panel/tareas.html, apps/panel/templates/panel/fila_tarea.html, tests/test_panel.py.
Criterio: Formulario minimalista tipo chat. Asignación automática de agente con modelo activo. Botón de eliminar tarea (POST) funcional. Tests en verde.
Estado: completado (2026-11-13).

14a: backend de asignación automática y eliminación de tareas.
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 62%]
...........................................                              [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
115 passed, 1 warning in 152.40s (0:02:32)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: crear_tarea ya no exige agente_id. Si falta, asigna el primer agente con
modelo activo mediante
Agente.objects.filter(modelo__activo=True).select_related("modelo").order_by("pk").first();
si no hay ninguno muestra "No hay agentes activos disponibles" sin crear fila ni
encolar. La tarea se sigue encolando con ejecutar_tarea(tarea.pk). eliminar_tarea
lleva @login_required y @require_POST: el POST borra y redirige a lista_tareas, y
el GET devuelve 405. La ruta es tarea/<int:pk>/eliminar/ con name='eliminar_tarea'.
Tests: test_crear_tarea_exitoso ya no envía agente_id y comprueba la asignación
automática; test_crear_tarea_sin_agente_seleccionado pasó a
test_crear_tarea_sin_agentes_activos; se añadieron test_eliminar_tarea_exitoso y
test_eliminar_tarea_get_no_permitido. La advertencia RemovedInDjango60Warning de
URLField es preexistente.

14b: rediseño tipo chat de crear_tarea.html y botón Eliminar en el listado.
COMPLETADO (2026-11-13). Paso 14 completo.
Evidencia (2026-11-13):
```
$ .venv\Scripts\python.exe -m pytest -q
........................................................................ [ 61%]
.............................................                            [100%]
=============================== warnings summary ===============================
tests/test_panel.py::TestPanel::test_aprobar_cambia_estado
  C:\Users\Drogo\Downloads\ARM agentes\.venv\Lib\site-packages\django\db\models\fields\__init__.py:1148: RemovedInDjango60Warning: The default scheme will be changed from 'http' to 'https' in Django 6.0. Pass the forms.URLField.assume_scheme argument to silence this warning, or set the FORMS_URLFIELD_ASSUME_HTTPS transitional setting to True to opt into using 'https' as the new default scheme.
    return form_class(**defaults)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
117 passed, 1 warning in 160.91s (0:02:40)

$ .venv\Scripts\python.exe manage.py check
System check identified no issues (0 silenced).
```
Notas: crear_tarea.html pasa a una tarjeta blanca de radio 12px y sombra suave
centrada a 760px. El contenido principal es un textarea de rows=12 con
placeholder "Escribe o pega aquí el contenido que quieres procesar..."; debajo
una fila flex con gap 16px contiene la keyword opcional y el select de agente
opcional, cuya primera opción vacía es "Asignación automática" (se eliminó el
required para permitir el reparto automático de 14a). Las instrucciones
adicionales se conservan en un textarea rows=3 y el botón "Procesar con IA" es
primario, azul #0071E3, de ancho completo y padding 14px 28px. Inputs, select y
textareas usan borde #D2D2D7, radio 8px y foco #0071E3 con halo suave; bajo
640px la fila keyword/agente pasa a columna. fila_tarea.html añade un formulario
POST con csrf_token a eliminar_tarea y el botón .btn-eliminar-tarea; tareas.html
define su estilo (fondo transparente, borde y texto #FF3B30, radio 6px, padding
4px 8px, 0.75rem y hover con fondo #FF3B30 y texto blanco). No se tocaron
views.py ni urls.py. Tests nuevos en tests/test_panel.py:
test_crear_tarea_formulario_chat (botón, rows=12, placeholder, keyword, agente,
instrucciones y opción vacía) y test_lista_muestra_formulario_eliminar (form
POST con la URL de borrado y la clase del botón). La advertencia
RemovedInDjango60Warning de URLField sigue siendo preexistente.
Pendiente: el botón Eliminar no pide confirmación antes de borrar; valorar un
diálogo de confirmación. Revisar en navegador el responsive de la fila
keyword/agente.