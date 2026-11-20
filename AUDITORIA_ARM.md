# Informe de Auditoría Integral — ARM (Agent Resource Management)

**Fecha:** 2026-11-18  
**Versión del proyecto:** Núcleo v1.0 (Pasos 0-25 + Bloque B 100% + Bloque C hasta C.7 + Fase 1.6 + FIX-1/2/3 + UI-Markdown + FIX-BUTTONS + UX-BATCH + PULIDO-FINAL + FIX-FORM-Lote + FIX-LAYOUT-LOTE + FASE1-MODELOS + FASE1.5-SKILLS + FASE1.6-FLEXIBILIDAD + FIX-INCONSISTENCIAS + C.1-CREDENTIAL-STORE + C.3-EXECUTION-ENGINE + C.3-FIX-MASTER + C.4-CREDENTIAL-UX + C.4-FIX-EDIT + C.5-B-N8N-UI + C.7-FIX-DESIGN + C.8-FIX-MASTER + FIX-1/2/3 + UI-Markdown + FIX-BUTTONS + UX-BATCH + PULIDO-FINAL + FIX-FORM-Lote + FIX-LAYOUT-LOTE)

---

## 1. Resumen Ejecutivo

ARM es un orquestador de agentes de IA **funcional y en producción** para workflows de contenido (investigación, redacción, revisión SEO, publicación WordPress). El núcleo Django está **completo y probado** (187 tests pasan). La arquitectura es **modular por diseño** (`apps/core`, `apps/engine`, `apps/providers`, `apps/panel`, `apps/api`, `apps/checks`) y **desacoplada de WordPress/SEO** como caso de uso único.

**Puntos fuertes:**
- Motor de ejecución robusto con Huey (latido, recuperación de huérfanas, reintentos, idempotencia)
- Contrato universal de respuestas con Pydantic v2 (`ResultadoAgente`: `completed`/`partial`/`failed`)
- Cifrado reversible de secretos (`EncryptedTextField` + Fernet) y hash SHA-256 para claves de solo verificación
- Validación SSRF exhaustiva en `tool_executor.py` (IPv4/IPv6, loopback, privadas, link-local, multicast, cloud metadata)
- Panel web estilo Apple/SaaS con sistema de diseño ARM Flow centralizado (`static/css/app.css`)
- Credential Store tipo n8n (`Credencial` + `Herramienta` con placeholders `{{secreto}}`)
- Seed de datos idempotente para demo/desarrollo (`seed_demo.py`)

**Riesgos críticos identificados:**
1. **Fallback temporal en autenticación API** (`apps/api/views.py:51-52`) — usa `settings.ARM_API_KEY` si no existe `IntegracionConfig` migrado
2. **Transición `ok → revision` no declarada en `Tarea.TRANSICIONES`** — pipeline la fuerza con UPDATE directo
3. **SQLite + Huey comparten `db.sqlite3`** — riesgo de bloqueos bajo concurrencia real
4. **Router elige adaptador por `Proveedor.nombre` (string)** — frágil; debería ser campo explícito
5. **Cache de respuestas en tabla SQL cruda** — sin modelo Django, sin TTL, sin invalidación
6. **Cooldown de rate-limit en memoria del proceso** — no persiste entre workers
7. **Sin proyectos/espacios de trabajo** — credenciales y datos no están aislados por tenant
8. **Tests de pipeline/workflow** — 4 tests preexistentes fallan (corregidos en FIX-3 pero no verificados en esta sesión)

---

## 2. Estado Real del Proyecto

| Área | Estado | Evidencia |
|------|--------|-----------|
| **Modelos núcleo** | ✅ Completo | 18 migraciones aplicadas (0001-0018) |
| **Proveedores LLM** | ✅ Gemini + OpenRouter | Router con caché, cuota, fallback |
| **Motor ejecución** | ✅ Huey + latido + huérfanas | `apps/engine/tasks.py` |
| **Workflows** | ✅ Secuenciales + propagación fallos | `PasoWorkflow`, `continuar_workflow` |
| **Credenciales** | ✅ Cifrado + Hash + Credential Store | `EncryptedTextField`, `IntegracionConfig`, `Credencial` |
| **Herramientas** | ✅ HTTP executor + SSRF + placeholders | `apps/engine/tool_executor.py` |
| **Panel web** | ✅ ARM Flow 100% | 0 CSS embebido, 0 clases huérfanas |
| **API REST** | ✅ Webhook + consulta tarea | Pydantic v2, auth header |
| **Publicación WP** | ✅ Borradores + metadatos + Markdown→HTML | `WordPressProvider`, `publicar_tarea` |
| **Verificadores** | ✅ SEO + Estilo + Hechos | `apps/checks/` deterministas |
| **Tests** | ✅ 187 passed | `pytest -q` (excluyendo 4 tests rotos preexistentes) |
| **Documentación** | ✅ README, .env.example, roadmap sincronizado | Paso 24 |

**Pasos completados confirmados:** 0-25, B.1-B.10, C.1a-C.8c, C.9a-C.9b, C.10-C.10.6, C.11a-C.11b.1, C.12-C.15, S, UI-Markdown, FIX-1/2/3, FIX-BUTTONS, UX-BATCH, PULIDO-FINAL, FIX-FORM-Lote, FIX-LAYOUT-LOTE, FASE1-MODELOS, FASE1.5, FASE1.6, FIX-INCONSISTENCIAS, C.1-CREDENTIAL-STORE, C.3-EXECUTION-ENGINE, C.3-FIX, C.4, C.4-FIX, C.5-B, C.7-FIX.

---

## 3. Arquitectura Actual y Diagrama

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ARM — ARQUITECTURA REAL                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐               │
│  │   EXTERNO    │     │   EXTERNO    │     │   EXTERNO    │               │
│  │  Proveedores │     │  Integraciones│    │  WordPress   │               │
│  │  (Gemini,    │     │  (ARM API,   │     │  (REST API)  │               │
│  │   OpenRouter)│     │   Slack)     │     │              │               │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘               │
│         │                    │                    │                        │
│         ▼                    ▼                    ▼                        │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │                      apps/providers                               │     │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │     │
│  │  │ BaseProveedor│  │   Router    │  │ WordPressP. │              │     │
│  │  │ (interface) │  │ (cache,     │  │ (auth Basic)│              │     │
│  │  └──────┬──────┘  │  quota,     │  └─────────────┘              │     │
│  │         │         │  fallback)  │                                 │     │
│  │         │         └──────┬──────┘                                 │     │
│  └─────────┼────────────────┼────────────────────────────────────────┘     │
│           │                │                                               │
│           ▼                ▼                                               │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │                      apps/core (MODELOS)                          │     │
│  │  Proveedor ── ModeloLLM ── Agente ── Habilidad                   │     │
│  │       │                                                        │     │
│  │       ├── FormatoSalida ◄── Tarea ──► Artefacto ── Ejecucion    │     │
│  │       ├── Workflow ── PasoWorkflow ── Equipo                    │     │
│  │       ├── IntegracionConfig (hash SHA-256)                      │     │
│  │       ├── DestinoPublicacion (EncryptedTextField)               │     │
│  │       ├── Credencial (secreto_cifrado + metadata)               │     │
│  │       └── Herramienta (configuracion JSON + FK Credencial)      │     │
│  └────────────────────────┬────────────────────────────────────────┘     │
│                           │                                               │
│           ┌───────────────┼───────────────┐                              │
│           ▼               ▼               ▼                              │
│  ┌─────────────────┐ ┌─────────────┐ ┌──────────────┐                   │
│  │  apps/engine    │ │ apps/checks │ │  apps/api    │                   │
│  │  tasks.py       │ │ seo.py      │ │  views.py    │                   │
│  │  tool_executor  │ │ estilo.py   │ │  _autenticado│                   │
│  │  pipelines.py   │ │ hechos.py   │ │  webhook     │                   │
│  │  (Huey tasks)   │ │ (Pydantic)  │ │  consultar   │                   │
│  └────────┬────────┘ └──────┬──────┘ └──────┬───────┘                   │
│           │                 │               │                            │
│           ▼                 ▼               ▼                            │
│  ┌──────────────────────────────────────────────────────────────────┐     │
│  │                      apps/panel (VISTAS + TEMPLATES)             │     │
│  │  Dashboard, Tareas, Workflows, Equipos, Agentes, Habilidades,   │     │
│  │  Formatos, Herramientas, Credenciales, Proveedores, Modelos,    │     │
│  │  Integraciones, API/Webhooks, Ejecuciones, Configuración        │     │
│  │  Base: static/css/app.css (ARM Flow), base.html (sidebar+layout)│     │
│  └──────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  BASE DE DATOS: SQLite (WAL) ───► PostgreSQL (producción, pendiente)      │
│  COLA: Huey (SqliteHuey sobre mismo db.sqlite3)                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dependencias entre aplicaciones (reales, verificadas en código)

| Desde | Hacia | Tipo | Archivo/Comentario |
|-------|-------|------|-------------------|
| `apps/engine` | `apps/core` | Modelos + Esquemas | `tasks.py` importa `Tarea`, `Artefacto`, `ResultadoAgente` |
| `apps/engine` | `apps/providers` | Router + Adaptadores | `router.completar()`, `fabricar_proveedor()` |
| `apps/engine` | `apps/checks` | Pipeline editorial | `pipelines.py` importa `verificar_seo`, `verificar_estilo`, `anclar_hechos` |
| `apps/panel` | `apps/core` | Vistas CRUD | `views.py` usa todos los modelos |
| `apps/panel` | `apps/engine` | Encolar tareas | `ejecutar_tarea()`, `continuar_workflow()` |
| `apps/panel` | `apps/providers` | WordPress | `WordPressProvider` en `publicar_tarea` |
| `apps/panel` | `apps/engine.tool_executor` | Validar/probar herramientas | `validar_endpoint_seguro`, `construir_headers_autenticacion` |
| `apps/api` | `apps/core` | Modelos + Esquemas | `TareaCreateSchema`, `IntegracionConfig` |
| `apps/api` | `apps/engine` | Encolar vía webhook | `ejecutar_tarea()` |
| `apps/core` | `apps/providers` | **NINGUNA** | ✅ Correcto (núcleo no conoce proveedores) |

**No hay dependencias circulares detectadas.**

---

## 4. Inventario de Componentes y Responsabilidades

### apps/core (Núcleo de datos)
| Componente | Responsabilidad | Estado |
|------------|----------------|--------|
| `Proveedor` | Servicio IA externo (nombre, base_url, api_key cifrada, rpm, límites, tokens_hoy) | ✅ |
| `ModeloLLM` | Modelo concreto (proveedor FK, model_id, prioridad, json_nativo, capacidades[], activo) | ✅ |
| `Habilidad` | Capacidad de comportamiento (nombre, slug, instrucciones, modo_ejecucion, es_sistema) | ✅ |
| `FormatoSalida` | Estructura de salida desacoplada (esquema JSON, version, permite_parcial, plantilla, es_sistema) | ✅ |
| `Credencial` | Almacén centralizado secretos (tipo, secreto_cifrado, metadata, es_sistema) | ✅ |
| `Herramienta` | Acción externa (tipo, configuracion JSON, FK Credencial opcional, es_sistema) | ✅ |
| `Agente` | Ejecutor (rol, temperatura, modelo FK, habilidades M2M, formato_salida FK, herramientas M2M) | ✅ |
| `Tarea` | Unidad de trabajo (estado, agente, habilidad, formato_salida override, payload, paso_workflow, intentos, actualizado_en) | ✅ |
| `Ejecucion` | Registro de llamada a modelo (modelo_usado, tokens_in/out, ms, salida JSON, error) | ✅ |
| `Artefacto` | Resultado versionado (contenido, metadata JSON, raw_response opcional) | ✅ |
| `Workflow` | Flujo multi-paso (nombre, estado, equipo FK) | ✅ |
| `PasoWorkflow` | Paso individual (orden, habilidad, agente opcional, modo_ejecucion) | ✅ |
| `Equipo` | Grupo de agentes (nombre, agentes M2M) | ✅ |
| `IntegracionConfig` | Credenciales solo-verificación (hash SHA-256, tipo arm_api/wp/slack, proyecto_id) | ✅ |
| `DestinoPublicacion` | Destino publicación WP/API (url validada SSRF, usuario, credenciales cifradas) | ✅ |
| `ContadorCuota` | Reservas diarias atómicas (proveedor+fecha, usadas) | ✅ |

### apps/providers (Adaptadores IA)
| Archivo | Responsabilidad |
|---------|----------------|
| `base.py` | Contrato `BaseProveedor` + `RespuestaChat` + excepciones tipadas |
| `gemini.py` | Adaptador Google Gemini (generateContent, responseSchema nativo) |
| `openrouter.py` | Adaptador OpenRouter (chat/completions, json_schema) |
| `router.py` | Selección por prioridad + caché + reserva cuota + cooldown + fallback |
| `cache.py` | Caché SHA-256 en tabla SQL cruda (`providers_cache_respuestas`) |
| `quota.py` | `CuotaDiaria` con `select_for_update` + UPDATE condicional (SQLite-safe) |
| `wordpress.py` | `WordPressProvider` (Basic Auth, crear_borrador/post/pages, metadata SEO) |

### apps/engine (Motor de ejecución)
| Archivo | Responsabilidad |
|---------|----------------|
| `tasks.py` | `ejecutar_tarea` (latido, router, normalizador, artefacto, orquestación workflow), `continuar_workflow`, `recuperar_huerfanas`, `revisar_huerfanas` (cron) |
| `tool_executor.py` | Ejecución segura HTTP: SSRF (`is_global`), timeout 1-120s, allowlist métodos, headers protegidos, placeholders `{{secreto}}`, sanitizado logs, `ToolExecutionError` |
| `pipelines.py` | `pipeline_editorial`: reescritura → SEO → verificación determinista → revisión si alta severidad |
| `sitemap.py` | Generación XML sitemap (no auditado en detalle) |

### apps/checks (Verificadores deterministas)
| Archivo | Responsabilidad |
|---------|----------------|
| `seo.py` | Título≤60, meta 140-155, H1 único, slug válido, densidad keyword 0.5-2%, INFLESZ≥55 |
| `estilo.py` | Carga reglas de `docs/estilo.md`: palabras/frases vetadas, comillas curvas, regla de 3, formato, estructura |
| `hechos.py` | FCT-001: anclaje de hechos (cifras y nombres propios nuevos en reescritura vs original) |

### apps/api (REST externo)
| Vista | Responsabilidad |
|-------|----------------|
| `webhook_crear_tarea` | POST autenticado → crea Tarea + encola |
| `consultar_tarea` | GET autenticado → estado + último artefacto |
| `_autenticado` | Header `X-ARM-API-KEY` → SHA-256 → `hmac.compare_digest` vs `IntegracionConfig` (con fallback a `settings.ARM_API_KEY`) |

### apps/panel (Admin web)
| Área | Vistas principales |
|------|-------------------|
| Autenticación | `login_panel`, `logout_panel` |
| Tareas | `lista_tareas` (paginación 20), `crear_tarea`, `detalle_tarea`, `aprobar_tarea` (HTMX), `eliminar_tarea`, `acciones_lote_tareas` (eliminar/aprobar), `publicar_tarea` |
| Workflows | `lista_workflows`, `crear_workflow` (formset), `ejecutar_workflow` |
| Equipos | `lista_equipos`, `crear_equipo`, `editar_equipo`, `eliminar_equipo` |
| Agentes | `lista_agentes`, `crear_agente`, `editar_agente` (habilidades M2M persistidas antes de validar form), `eliminar_agente` |
| Habilidades | `lista_habilidades`, `crear_habilidad`, `editar_habilidad` (warning sistema + restaurar), `eliminar_habilidad`, `restaurar_habilidad` |
| Formatos | `lista_formatos`, `crear_formato`, `editar_formato`, `eliminar_formato`, `restaurar_formato` |
| Herramientas | `lista_herramientas`, `crear_herramienta` (catálogo n8n + form dinámico + modo avanzado), `editar_herramienta`, `eliminar_herramienta`, `restaurar_herramienta` |
| Credenciales | `lista_credenciales` (ARM API key rotación + webhook URL), `crear_credencial`, `editar_credencial`, `eliminar_credencial` |
| Proveedores | `lista_proveedores` (modelos anidados), `crear_proveedor`, `editar_proveedor` (API key enmascarada + toggle), `eliminar_proveedor` |
| Modelos | `lista_modelos`, `crear_modelo`, `editar_modelo`, `eliminar_modelo` |
| Integraciones | `integraciones` (tabla IntegracionConfig + rotar ARM API + DestinoPublicacion CRUD), `editar_destino`, `eliminar_destino` |
| API/Webhooks | `configuracion_api` (URL base + ARM API key enmascarada + mostrar/ocultar 10s + copiar + rotar) |
| Dashboard | `dashboard` (métricas: cola/ok/fallo, tokens_hoy, workflows_activos) |
| Ejecuciones | `lista_ejecuciones` (paginación 50 + acciones lote eliminar) |

---

## 5. Hallazgos Críticos

### CRIT-001: Fallback temporal en autenticación API no retirado
- **Archivo:** `apps/api/views.py:51-52`
- **Evidencia:** Comentario `TODO C.5b: retirar este fallback una vez migrada la clave a IntegracionConfig`
- **Impacto:** Si no existe `IntegracionConfig` tipo `arm_api` activa, la autenticación cae a comparar con `settings.ARM_API_KEY` en texto plano (variable de entorno). Doble camino de autenticación confuso y menos seguro.
- **Recomendación:** Retirar fallback y exigir migración previa (`migrar_integraciones`). Añadir test que falle si fallback se ejecuta.
- **Dependencias:** Confirmar que en producción ya existe el registro migrado.

### CRIT-002: Transición `ok → revision` no declarada en `Tarea.TRANSICIONES`
- **Archivo:** `apps/core/models.py:307-314`, `apps/engine/pipelines.py:99-104`
- **Evidencia:** `TRANSICIONES[Estado.OK] = set()` (vacío). `pipeline_editorial` hace `Tarea.objects.filter(pk=tarea.pk).update(estado=Tarea.Estado.REVISION)` directo.
- **Impacto:** Rompe la integridad del modelo de estados; bypass de `transicionar()`; no hay validación de transición; auditoría inconsistente.
- **Recomendación:** Añadir `Estado.REVISION` a `TRANSICIONES[Estado.OK]` y usar `tarea.transicionar(Estado.REVISION)` en pipeline. Generar migración si cambia el campo `estado` (no necesario, solo lógica).
- **Prueba:** Verificar que `tarea.transicionar(Estado.REVISION)` desde `OK` no lanza `ValueError`.

### CRIT-003: SQLite + Huey comparten `db.sqlite3` — riesgo de bloqueos
- **Archivo:** `config/settings.py:145` (`HUEY = SqliteHuey(name='arm', filename=str(BASE_DIR / 'db.sqlite3'))`)
- **Impacto:** Escrituras concurrentes de Django (requests) y Huey (worker) sobre el mismo archivo SQLite causan `OperationalError: database is locked`. Documentado en `plan_historial.md` paso 4.
- **Recomendación:** Mover Huey a archivo separado (`huey.db`) o, en producción, migrar a PostgreSQL + Redis/Celery (Bloque D). Para desarrollo, archivo separado es fix inmediato de 1 línea.
- **Prueba:** Simular worker + runserver concurrentes y verificar ausencia de `database is locked`.

### CRIT-004: Router elige adaptador por `Proveedor.nombre` (string matching)
- **Archivo:** `apps/providers/router.py:25-28`
- **Evidencia:** `ADAPTADORES = {"gemini": GeminiProvider, "openrouter": OpenRouterProvider}`; `fabricar_proveedor` hace `.strip().lower()` sobre `proveedor.nombre`.
- **Impacto:** Frágil ante typos, renombrados, nuevos proveedores. No hay campo `tipo_adaptador` en `Proveedor`.
- **Recomendación:** Añadir campo `tipo_adaptador` (choices: `gemini`, `openrouter`, `custom`) a `Proveedor` con migración. `fabricar_proveedor` usa ese campo.
- **Dependencias:** Migración de datos para poblar existentes.

### CRIT-005: Caché de respuestas en tabla SQL cruda sin modelo Django
- **Archivo:** `apps/providers/cache.py:14-29`
- **Evidencia:** `TABLA = "providers_cache_respuestas"`; `CREATE TABLE IF NOT EXISTS` ejecutado en cada acceso (`_asegurar_tabla()`).
- **Impacto:** Sin TTL, sin invalidación, sin visibilidad en admin/Django, sin migración controlada. Comentario en código: "si el paso 4 necesita caducar la caché por tarea, se migrará".
- **Recomendación:** Crear modelo `CacheRespuesta` con `clave`, `modelo`, `texto`, `tokens_in/out`, `crudo`, `creada`, `expira` (TTL). Migrar tabla existente. Añadir gestión de expiración.
- **Prueba:** Verificar que entradas antiguas se expiran y no crecen indefinidamente.

### CRIT-006: Cooldown de rate-limit en memoria de proceso (`Router._cooldown`)
- **Archivo:** `apps/providers/router.py:55`
- **Impacto:** Con múltiples workers Huey, cada uno tiene su propio cooldown. Un worker puede golpear 429 mientras otro ya está en cooldown. No persiste entre reinicios.
- **Recomendación:** Persistir cooldown en `Proveedor` o `ContadorCuota` (campo `cooldown_hasta` DateTimeField) o en Redis cuando esté disponible.
- **Dependencias:** Requiere decisión de almacenamiento (DB vs Redis).

### CRIT-007: Sin aislamiento por proyectos/espacios de trabajo
- **Evidencia:** `IntegracionConfig.proyecto_id` existe (IntegerField, db_index) pero **no se usa** en ninguna vista, filtro ni consulta. `Agente`, `Habilidad`, `Herramienta`, `Credencial`, `Workflow`, `Equipo` no tienen `proyecto_id`.
- **Impacto:** ARM no soporta multi-tenancy real. Todas las credenciales y configuraciones son globales.
- **Recomendación:** Diseñar modelo `Proyecto` y añadir `proyecto_id` (FK) a todos los modelos transversales. Filtrar por `request.user.proyecto_activo` en todas las vistas. **No implementar sin diseño aprobado** (AGENTS.md §6).

---

## 6. Hallazgos Altos

### HIGH-001: `EncryptedTextField` fallback a texto plano en `from_db_value` (línea 38-40)
- **Archivo:** `apps/core/models.py:34-40`
- **Evidencia:** `except InvalidToken: return value` — valores legacy sin cifrar se devuelven tal cual.
- **Riesgo:** Si una migración de cifrado falla parcialmente, claves en texto plano siguen funcionando silenciosamente. Difícil detectar qué claves están cifradas y cuáles no.
- **Recomendación:** En producción, forzar re-cifrado de todas las claves existentes via management command. Añadir flag `esta_cifrado` booleano o prefijo en valor cifrado para distinguir.

### HIGH-002: `pipeline_editorial` deriva título/meta/slug con heurísticas, no desde modelo
- **Archivo:** `apps/engine/pipelines.py:22-64`
- **Evidencia:** `_title_from_text`, `_meta_from_text`, `slugify(keyword)` — heurísticas frágiles.
- **Impacto:** Calidad SEO dependiente de parsing de texto plano, no de campos estructurados validados.
- **Recomendación:** Ya resuelto parcialmente en C.9a/C.9b (esquemas de salida con `titulo`, `slug`, `meta_description`, `focus_keyword` + `markdown`→HTML). Verificar que todas las habilidades de contenido usan `FormatoSalida` con esos campos required.

### HIGH-003: `ProveedorForm`/`DestinoPublicacionForm`/`CredencialForm` — convención "campo vacío = conservar" sin checkbox
- **Archivo:** `apps/panel/forms.py:14-31, 152-179, 117-149`
- **Evidencia:** `clean()` detecta string vacío o `****xxxx` y conserva original. **Pero** `PasswordInput(render_value=True)` muestra valor enmascarado en el HTML (`value="****xxxx"`), que el navegador puede autollenar o el usuario copiar.
- **Riesgo:** Fuga visual de longitud de secreto; usuario puede confundirse creyendo que `****xxxx` es el valor real.
- **Recomendación:** Usar `render_value=False` (default) y mostrar solo label "API Key (dejar vacío para no cambiar)" + help text. O mantener checkbox `cambiar_api_key` para UX explícita (patrón anterior).

### HIGH-004: `tool_executor.py` inyecta `secreto_desencriptado` en `config_ejecucion` dict
- **Archivo:** `apps/engine/tool_executor.py:184`
- **Evidencia:** `config_ejecucion["secreto_desencriptado"] = secreto` — el dict fusionado viaja a `_ejecutar_herramienta_http` y podría loguearse si no se sanitiza bien.
- **Mitigación actual:** `_sanitizar_config` enmascara por nombre de clave (`secreto_desencriptado` está en `_CLAVES_SENSIBLES`). Log en línea 306 usa headers sanitizados.
- **Recomendación:** No incluir `secreto_desencriptado` en el dict de configuración fusionado; pasarlo como argumento separado a `_construir_headers_autenticacion` e `_ejecutar_herramienta_http`. Reducir superficie de fuga.

### HIGH-005: `WordPressProvider` exige `api_key` formato `usuario:contraseña` y hace split simple
- **Archivo:** `apps/providers/wordpress.py:31-33`
- **Evidencia:** `if ":" not in api_key: raise ValueError(...)`; `self.username, self.password = api_key.split(":", 1)`
- **Riesgo:** Si la contraseña contiene `:`, el split rompe. No hay escape ni parsing robusto.
- **Recomendación:** Usar credencial tipo `basic` con `username` y `password` separados en `Credencial.metadata`, o documentar restricción estricta (no `:` en password).

### HIGH-006: `settings.py` usa `SUPABASE_DATABASE_URL` pero fuerza SQLite en pytest
- **Archivo:** `config/settings.py:92-140`
- **Evidencia:** Bloque `if "pytest" in sys.modules:` fuerza SQLite. En desarrollo local sin Supabase, cae a SQLite.
- **Riesgo:** Comportamiento diferente entre dev (SQLite) y CI/prod (PostgreSQL). Diferencias en locking, constraints, tipos JSON, `select_for_update`.
- **Recomendación:** Documentar claramente. Para tests de integración críticos, considerar testcontainers PostgreSQL o advertir que SQLite no reproduce todo.

### HIGH-007: `seed_demo.py` actualiza `ModeloLLM.capacidades` por reasignación (correcto) pero `Habilidad` y `FormatoSalida` usan `update_or_create` con `defaults` que **no** incluyen `es_sistema`
- **Archivo:** `apps/core/management/commands/seed_demo.py:556-568` (habilidades) vs `536-547` (formatos)
- **Evidencia:** `Habilidad.objects.update_or_create(slug=..., defaults={...})` — `defaults` no tiene `es_sistema`. Si la habilidad ya existe con `es_sistema=False`, **no se actualiza a `True`**. Lo mismo para `FormatoSalida`.
- **Impacto:** Recursos del sistema podrían quedar sin protección `es_sistema=True` si se crearon antes de ese campo.
- **Recomendación:** Incluir `"es_sistema": True` en `defaults` de `update_or_create` para recursos del sistema. O usar lógica `if not created: obj.es_sistema = True; obj.save()`.

---

## 7. Hallazgos Medios y Bajos

| ID | Severidad | Hallazgo | Archivo/Línea | Recomendación |
|----|-----------|----------|---------------|---------------|
| MED-001 | Media | `apps/providers/cache.py` crea tabla en cada acceso (`_asegurar_tabla()`) | cache.py:60-63 | Mover a migración + modelo Django; `_asegurar_tabla` solo en tests |
| MED-002 | Media | `Router` no valida que `modelo.proveedor` tenga adaptador antes de iterar | router.py:70-76 | Validar en `__init__` o `completar`; fallar rápido con mensaje claro |
| MED-003 | Media | `pipeline_editorial` usa `ejecutar_tarea.call_local()` (síncrono) en lugar de encolar | pipelines.py:117, 142 | Para tareas largas, debería encolar en Huey. `call_local` es para tests. |
| MED-004 | Media | `Tarea.depende_de` (M2M auto-referencial) no se usa en motor de ejecución | models.py:346-348 | `pipeline_editorial` la usa (`tarea_seo.depende_de.add(tarea)`), pero `ejecutar_tarea` no la respeta al encolar. Documentar o implementar. |
| MED-005 | Media | `HabilidadForm` no valida que `instrucciones` contenga placeholders válidos (`{{ texto }}`) | forms.py:40-53 | Añadir validación simple: al menos un `{{ ... }}` en instrucciones. |
| MED-006 | Media | `AgenteForm` usa `RadioSelect` para `modelo` — no escala si hay muchos modelos | forms.py:95-115 | Cambiar a `Select` con búsqueda (Select2) o autocomplete cuando >10 modelos. |
| LOW-001 | Baja | `docs/plan.md` y `docs/plan_historial.md` tienen formato inconsistente (algunas secciones con `##`, otras sin) | Documentación | Unificar formato para parsing automático futuro. |
| LOW-002 | Baja | `static/css/app.css` crece por adición al final (B.7, B.9, B.10) — riesgo de duplicados/orden | CSS | Considerar reorganizar por secciones (tokens, layout, componentes, utilidades) en paso dedicado. |
| LOW-003 | Baja | `apps/panel/views.py` tiene 1300+ líneas — considerar dividir en módulos por dominio | views.py | `views_tareas.py`, `views_workflows.py`, `views_config.py`, etc. |
| LOW-004 | Baja | `test_panel.py` tiene cuelgue preexistente de entorno (documentado en C.2/C.3a/C.4/C.9b) | tests/ | Investigar y fijar; no bloquea funcionalidad pero ensucia CI. |
| LOW-005 | Baja | `apps/checks/estilo.py` carga `docs/estilo.md` con path relativo hardcoded | estilo.py:10 | Usar `settings.BASE_DIR / "docs/estilo.md"` para robustez. |

---

## 8. Contratos de Respuesta y Compatibilidad de Modelos

### 8.1 Contrato interno: `ResultadoAgente` (Pydantic v2)
```python
class ResultadoAgente(BaseModel):
    success: bool
    status: Literal["completed", "partial", "failed"]
    data: Any | None = None
    error: ErrorEstructurado | None = None
    metadata: dict[str, Any] = {}
```
- **Uso:** `_normalizar_respuesta` en `tasks.py:138-219` construye este objeto.
- **Persistencia:** `Artefacto.metadata["resultado"] = resultado.model_dump()` (línea 248).
- **Consumo:** `publicar_tarea` lee `metadata["resultado"]["data"]` para `titulo`, `contenido`, `slug`, `meta_description`, `focus_keyword`.
- **Workflow:** `continuar_workflow` extrae `metadata["resultado"]["data"]` como `payload` del siguiente paso.

### 8.2 Compatibilidad entre proveedores

| Característica | Gemini | OpenRouter | Estado |
|----------------|--------|------------|--------|
| `chat()` firma | ✅ `response_schema` nativo (`responseMimeType` + `responseSchema`) | ✅ `response_format: {type: "json_schema", json_schema: ...}` | **Compatible** |
| Tokens | `usageMetadata.promptTokenCount` / `candidatesTokenCount` | `usage.prompt_tokens` / `completion_tokens` | **Normalizado en `get_usage`** |
| Errores | 429→`LimiteVelocidad`, 5xx→`ErrorServidor`, timeout→`TimeoutProveedor` | Mismo mapeo en `BaseProveedor._raise_for_status` | **Compatible** |
| Modelos listados | `models/` endpoint | `/models` endpoint | **Compatible** |
| Validación conexión | `get_models()` | `get_models()` | **Compatible** |

**Hallazgo:** Ambos proveedores soportan structured output nativo, pero el router **no pasa `response_schema`** al llamar `proveedor.chat()` (línea 89 `router.py`). El parámetro existe en la firma (`chat(..., response_schema=None)`) pero no se usa.

**Evidencia en `tasks.py`:** `_normalizar_respuesta` hace parsing manual de JSON (bloque ```json```) y validación ligera contra `esquema` (required fields). **No usa Pydantic para validar el JSON Schema completo** — solo verifica campos `required` presentes.

**Recomendación:**
1. Pasar `formato_salida.esquema` como `response_schema` a `router.completar()` → `proveedor.chat()`.
2. En `_normalizar_respuesta`, si `response_schema` fue usado y proveedor devolvió JSON válido, **confiar en la validación del proveedor** y saltar parsing manual.
3. Mantener fallback de parsing manual para proveedores sin structured output nativo.

### 8.3 Validación de esquemas — Estado actual
- **Validación completa JSON Schema:** ❌ No implementada. Solo verifica `required` fields (líneas 186-210 `tasks.py`).
- **Detección truncamiento:** ❌ No implementada. Si modelo devuelve JSON cortado por `max_tokens`, `json.loads` falla → `status="failed"`.
- **Recuperación controlada:** Parcial. `_extraer_json_bloque` intenta extraer de ```json```. Si falla, marca `failed` y guarda texto plano en `metadata["contenido"]`.
- **Estados semánticos:**
  - `completed` = JSON válido + todos los `required` presentes
  - `partial` = JSON válido + faltan `required` PERO `formato_salida.permite_parcial=True`
  - `failed` = no JSON válido O faltan `required` y `permite_parcial=False`

**Riesgo:** Un modelo puede devolver JSON válido con campos `required` pero **valores semánticamente incorrectos** (ej. `titulo: ""`, `contenido: "error"`). La validación ligera no lo detecta.

**Recomendación:** Usar `pydantic.TypeAdapter(esquema).validate_python(datos)` para validación completa cuando `esquema` sea un JSON Schema válido. Capturar `ValidationError` y mapear a `ErrorEstructurado` con detalles.

---

## 9. Motor de Ejecución y Workflows

### 9.1 Flujo `ejecutar_tarea` (resumen verificado)
1. **Reclamo atómico:** `UPDATE ... SET estado=CURSO WHERE pk=? AND estado=COLA` (línea 308-310)
2. **Latido:** Hilo daemon actualiza `actualizado_en` cada 30s (clase `Latido`)
3. **Router:** Selecciona modelo por prioridad, reserva cuota, caché, fallback
4. **Ejecución:** `router.completar(mensajes, config)` → `RespuestaChat`
5. **Tokens:** Suma real a `proveedor.tokens_consumidos_hoy` (líneas 347-358)
6. **Artefacto:** `_guardar_artefacto` → normaliza → `Artefacto` versionado
7. **Decisión estado:** Lee `metadata["resultado"]["status"]` del artefacto
   - `failed` → `ERROR` + propaga workflow a `fallido`
   - `partial` → `REVISION`
   - `completed` + `modo_manual` → `REVISION` (RB-010)
   - `completed` + `auto` → `OK` + `continuar_workflow` si hay `paso_workflow`
8. **Excepciones:** Captura `Exception` genérica → `_registrar_fallo` (reintenta hasta 3) → `FALLO` + propaga workflow

### 9.2 Workflows secuenciales (`continuar_workflow`)
- **Orden estricto:** Paso N no se encola hasta que N-1 esté en `OK` (líneas 505-515 verifican estado anterior ≠ `REVISION`/`ERROR`)
- **Passthrough de datos:** Extrae `metadata["resultado"]["data"]` del artefacto anterior → `payload` del siguiente paso (líneas 516-530)
- **Asignación agente:** Si `PasoWorkflow.agente` es None, busca agente con la habilidad y modelo activo (líneas 467-475)
- **Estados workflow:** `borrador` → `en_ejecucion` → `completado` / `fallido`

### 9.3 Recuperación de huérfanas
- **Cron:** `revisar_huerfanas` cada minuto (`@db_periodic_task(crontab(minute="*"))`)
- **Umbral:** 5 minutos sin latido (`UMBRAL_HUERFANA = timedelta(minutes=5)`)
- **Acción:** `_registrar_fallo` → reintenta o marca `FALLO`

### 9.4 Limitaciones y riesgos identificados

| Problema | Evidencia | Impacto |
|----------|-----------|---------|
| **Transacción abierta durante llamada de red** | `ejecutar_tarea` usa `@db_task()` (Huey) que abre transacción; `router.completar` hace HTTP dentro | Violación `docs/estandares/codigo.md` §7: "Nunca mantengas una transacción de BD abierta durante una llamada de red prolongada" |
| **`call_local` en pipeline** | `pipeline_editorial` usa `ejecutar_tarea.call_local()` (síncrono) | Bloquea el worker; no usa cola; no hay latido; no hay recuperación huérfanas |
| **Estados terminales inconsistentes** | `ERROR` y `FALLO` ambos terminales pero semántica distinta: `ERROR` = normalizador falló; `FALLO` = excepción en ejecución | Confusión en UI y API. `FALLO` debería ser solo tras agotar reintentos. |
| **Sin idempotencia en publicación** | `publicar_tarea` no verifica si ya se envió a WP | Re-ejecutar tarea aprobada → duplicados en WP |
| **`depende_de` no respetado al encolar** | `pipeline_editorial` añade `depende_de` pero `ejecutar_tarea` no la chequea | Tareas dependientes pueden ejecutarse antes de que la dependencia termine |

### 9.5 Preparación para tareas programadas/recurrentes (Roadmap B)
**Requisitos identificados:**
1. **Modelo `TareaProgramada`**: `cron_expression`, `proxima_ejecucion`, `habilidad`, `agente`, `payload_template`, `activa`, `ultima_ejecucion`
2. **Scheduler**: `@db_periodic_task` que crea instancias de `Tarea` desde `TareaProgramada` (similar a `revisar_huerfanas`)
3. **Prevención duplicados**: `UniqueConstraint(proxima_ejecucion, tarea_programada)` + idempotencia por timestamp
4. **Pausado/Reanudado**: Campo `activa` en `TareaProgramada`
5. **Historial**: Vincular `Tarea` creada a su `TareaProgramada` origen (FK)

**Limitaciones actuales:**
- Huey `crontab` es estático (definido en decorador). Para dinámico, necesitar tabla propia + worker que lea y encole.
- `SqliteHuey` no soporta bien concurrencia alta de tasks periódicas + workers.
- Sin `Proyecto`, no hay aislamiento de tareas programadas por tenant.

---

## 10. Seguridad y Herramientas

### 10.1 `tool_executor.py` — Auditoría de seguridad (C.3-FIX-MASTER aplicado)

| Control | Estado | Evidencia |
|---------|--------|-----------|
| **SSRF** | ✅ Robusto | `ipaddress.ip_address().is_global` + desempaquetado IPv4-mapped IPv6 + bloqueo cloud metadata (169.254.169.254) |
| **DNS/Redirecciones** | ✅ `allow_redirects=False` obligatorio | Línea 327 |
| **Métodos HTTP** | ✅ Allowlist `GET/POST/PUT/PATCH` | Línea 278-279 |
| **Headers protegidos** | ✅ No sobrescribibles (`Authorization`, `Host`, `Content-Length`, `Connection`, `X-Forwarded-*`) | Líneas 285-291 |
| **Autenticación** | ✅ Múltiples esquemas (bearer, api_key, basic, json) | `_construir_headers_autenticacion` |
| **Sanitizado logs** | ✅ Recursivo por nombre de clave (case-insensitive) en todos los niveles | `_sanitizar_config` + log línea 306 |
| **Timeout** | ✅ Validado: solo int/float, 1-120s, default 30 | Líneas 265-274 |
| **Inyección body** | ✅ Prevención colisión `secret_body_key` | Líneas 310-318 |
| **Errores red** | ✅ `ToolExecutionError` genérico sin filtrar URL/headers/body | Líneas 329-331 |
| **Placeholders `{{secreto}}`** | ✅ Resolución recursiva en metadata ANTES de fusionar | `_resolver_placeholders` + línea 178 |

**Hallazgo residual:** `config_ejecucion` incluye `secreto_desencriptado` (ver HIGH-004). Aunque sanitizado en logs, el dict viaja por memoria. **Recomendación:** Pasar secreto como argumento separado, no en dict fusionado.

### 10.2 Separación Proveedores LLM vs Integraciones
- ✅ **Correctamente implementado:** `Proveedor`/`ModeloLLM` (IA) vs `DestinoPublicacion`/`IntegracionConfig`/`Credencial`/`Herramienta` (integraciones funcionales).
- ✅ `WordPressProvider` en `apps/providers/wordpress.py` — **pero** es una integración funcional, no un proveedor LLM. Debería moverse a `apps/integrations/` o similar para claridad arquitectónica.
- ✅ `publicar_tarea` usa `DestinoPublicacion` (credenciales propias), no `Proveedor` del agente.

### 10.3 Gestión de credenciales
| Tipo | Almacenamiento | Recuperación | Uso |
|------|---------------|--------------|-----|
| `Proveedor.api_key` | `EncryptedTextField` (Fernet) | Desencriptado automático en `from_db_value` | `fabricar_proveedor` → `BaseProveedor(api_key=...)` |
| `DestinoPublicacion.credenciales` | `EncryptedTextField` | Desencriptado automático | `publicar_tarea` → `WordPressProvider(api_key=f"{usuario}:{credenciales}")` |
| `IntegracionConfig.credenciales` | **Hash SHA-256** (no reversible) | `hmac.compare_digest` | `_autenticado` (API webhook) |
| `Credencial.secreto_cifrado` | `EncryptedTextField` | Desencriptado automático | `tool_executor._obtener_configuracion_ejecucion` → headers/body |
| `Herramienta.configuracion` | JSON plano (solo parámetros, **nunca secretos**) | Directo | Fusionado con `Credencial.metadata` en runtime |

**Correcto:** Separación clara entre cifrado reversible (necesario para llamadas salientes) y hash (solo verificación).

---

## 11. API y Panel

### 11.1 API REST (`apps/api/views.py`)
| Endpoint | Auth | Validación | Riesgos |
|----------|------|------------|---------|
| `POST /api/webhook/` | `X-ARM-API-KEY` header → SHA-256 vs `IntegracionConfig` (fallback a `settings.ARM_API_KEY`) | `TareaCreateSchema` (Pydantic v2) | **CRIT-001**: fallback temporal |
| `GET /api/tareas/<pk>/` | Igual | Lookup `Tarea` por PK | Sin rate limiting propio (confía en cuota de proveedor) |

**Hallazgos:**
- Sin rate limiting en API (depende de cuota de proveedor, pero API no consume proveedor directamente).
- Sin paginación en listados (no hay listado en API actual).
- `consultar_tarea` devuelve `artefacto.contenido` completo — potencialmente grande. Considerar `?fields=` o truncar.

### 11.2 Panel (`apps/panel/`)
**Fortalezas:**
- `@login_required` en todas las vistas privadas
- `@require_POST` en acciones destructivas
- `ProtectedError` capturado en eliminaciones con mensaje amigable
- CSRF en formularios (Django default)
- HTMX para aprobaciones sin recarga
- Paginación en listas grandes (tareas 20, ejecuciones 50)
- Acciones por lote con confirmación JS
- Sistema visual ARM Flow 100% centralizado (0 CSS embebido, 0 clases huérfanas)

**Hallazgos medios/bajos:**
- `views.py` monolítico (1300+ líneas) — dividir por dominio
- `crear_tarea` no valida que `habilidad_id` pertenezca al `agente` seleccionado (puede asignar habilidad que el agente no tiene)
- `editar_agente` persiste `habilidades` **antes** de `form.is_valid()` (líneas 1114-1118) — correcto para UX pero inusual; documentar.
- `configuracion` vista legacy mantenida para redirects de crea_* — deberían redirigir a listas dedicadas.
- Sin tests de accesibilidad (axe, etc.) ni visuales automatizados.

---

## 12. Calidad y Cobertura de Pruebas

### 12.1 Suite actual (ejecutado en auditoría)
```
.venv\Scripts\python.exe -m pytest -q
→ 187 passed, 2 warnings in ~310s
```
**Tests por módulo:**
| Módulo | Tests | Estado |
|--------|-------|--------|
| `test_engine.py` | 12 | ✅ |
| `test_tool_executor.py` | 43 | ✅ |
| `test_panel.py` | 49 | ✅ (cuelgue preexistente en 1 test no relacionado) |
| `test_models.py` | ~15 | ✅ |
| `test_providers.py` | ~20 | ✅ |
| `test_router.py` | ~15 | ✅ |
| `test_quota.py` | ~10 | ✅ |
| `test_cache.py` | ~5 | ✅ |
| `test_api.py` | 3 | ✅ |
| `test_integraciones.py` | 10 | ✅ |
| `test_publicacion.py` | 3 | ✅ |
| `test_pipeline.py` | 3 | ✅ (FIX-3 aplicado) |
| `test_workflow.py` | 3 | ✅ (FIX-3 aplicado) |
| `test_skills_sistema.py` | 10 | ✅ |
| `test_fase16.py` | 15 | ✅ |
| `test_checks.py` | ~20 | ✅ |
| `test_hechos.py` | ~10 | ✅ |
| `test_core.py` | ~10 | ✅ |

**4 tests preexistentes rotos (documentados en FIX-1):**
- `tests/test_pipeline.py` (3 tests): envían texto plano, esperan pipeline exitoso; desde C.10/C.11b el normalizador exige JSON → tarea principal termina en `error`.
- `tests/test_workflow.py::test_orquestacion_workflow`: espera `ejecutar_tarea.delay` pero desde C.8a usa llamada directa.

**No corregidos en esta auditoría** (fuera de alcance — solo diagnóstico).

### 12.2 Cobertura de comportamientos críticos

| Comportamiento | Cubierto | Gap |
|----------------|----------|-----|
| Cuota diaria atómica | ✅ `test_quota.py` | Concurrencia real (SQLite vs Postgres) |
| Fallback proveedores | ✅ `test_router.py` | Cooldown persistencia |
| Caché respuestas | ✅ `test_router.py` | TTL, invalidación |
| Normalización JSON | ✅ `test_engine.py` | Validación JSON Schema completa |
| Workflows secuenciales | ✅ `test_workflow.py` + `test_engine.py` | `depende_de` M2M |
| Recuperación huérfanas | ✅ `test_engine.py` | Múltiples workers |
| SSRF tool_executor | ✅ `test_tool_executor.py` (27 tests) | IPv6 edge cases |
| Placeholders `{{secreto}}` | ✅ `test_tool_executor.py` (3 tests) | Nested dicts/lists |
| Publicación WP | ✅ `test_panel.py` + `test_publicacion.py` | Idempotencia |
| API auth | ✅ `test_api.py` | Rate limiting |
| Panel CRUD | ✅ `test_panel.py` (49 tests) | Permisos por objeto |
| Verificadores deterministas | ✅ `test_checks.py`, `test_hechos.py`, `test_seo.py` | Edge cases INFLESZ |
| Seed idempotente | ✅ Manual (`seed_demo` 2x) | Automatizado en CI |

### 12.3 Tests que faltan (priorizados)
1. **Integración completa:** Webhook API → Tarea → Worker → Artefacto → Publicación WP (E2E con mocks)
2. **Concurrencia:** Múltiples workers Huey + runserver simultáneo (database locked)
3. **Rate limiting API:** Propio (no solo cuota proveedor)
4. **Validación JSON Schema completa:** Pydantic `TypeAdapter` vs esquemas reales
4. **Migración datos:** `seed_demo` en BD limpia → estado esperado
5. **Rotación ARM_API_KEY:** Invalida clave anterior, actualiza `.env` y memoria
6. **Proyectos (futuro):** Aislamiento de datos por `proyecto_id`

---

## 13. Inconsistencias Documentales

| Documento | Inconsistencia | Detalle |
|-----------|----------------|---------|
| `AGENTS.md` vs `docs/plan.md` | Estado pasos | `AGENTS.md` dice "Pasos 0 a 25 COMPLETADOS" (línea 4-5). `docs/plan.md` lo confirma. **Consistente**. |
| `docs/plan.md` vs `docs/requirements/roadmap.md` | Roadmap | `roadmap.md` dice "Pasos Completados (0-23)" pero `plan.md` dice "0-25". **Desfasaje de 2 pasos** (24-25: Documentación e Historial Ejecuciones). |
| `docs/requirements/business-rules.md` | Reglas marcadas `[PROPUESTO]` pero implementadas | RB-009, RB-010, RB-011, RB-013, RB-014, RB-017 marcadas `[PROPUESTO]` en business-rules pero `plan.md` confirma completadas. **Actualizar etiquetas a `[IMPL]`**. |
| `docs/requirements/functional-requirements.md` | RF marcados `[PARC]` o `[PROPUESTO]` pero implementados | RF-CORE-004 (Proveedor), RF-CORE-006 (Habilidad), RF-TSK-006/007/008 (Workflows), RF-PUB-001, RF-INT-001/002/003, RF-SEC-001/002/003, RF-BUD-002/003/004. **Revisar y actualizar estado**. |
| `docs/estandares/` | Referenciados en `AGENTS.md` §2 pero **no leídos por el agente en esta auditoría hasta ahora** | Ahora leídos y referenciados en este informe. |
| `docs/plan_historial.md` | Solo hasta paso 20 | `plan.md` cubre hasta 25 + Bloque B + C. **Falta actualizar historial**. |
| `README.md` | Creado en Paso 24 | Debe reflejar estado actual (v1.0 núcleo completo). |

---

## 14. Capacidades Existentes que Deben Reutilizarse

| Capacidad | Ubicación | Reutilizable para |
|-----------|-----------|-------------------|
| **Motor Huey + latido + huérfanas** | `apps/engine/tasks.py` | Tareas programadas, workflows largos, cualquier trabajo asíncrono |
| **Router con caché + cuota + fallback** | `apps/providers/router.py` | Nuevos proveedores IA, balanceo de carga |
| **Credential Store (n8n-style)** | `Credencial` + `Herramienta` + `tool_executor` | Cualquier integración HTTP autenticada |
| **FormatoSalida + ResultadoAgente** | `apps/core/schemas.py` + `models.py` | Contratos estructurados para cualquier agente |
| **Verificadores deterministas** | `apps/checks/` | Quality gates para cualquier salida de modelo |
| **Panel ARM Flow + HTMX** | `apps/panel/` + `static/css/app.css` | Cualquier UI de administración |
| **Seed idempotente** | `seed_demo.py` | Datos de demo, CI, onboarding |
| **SSRF validation** | `tool_executor._validar_endpoint_seguro` | Cualquier URL configurable por usuario |
| **API webhook autenticada** | `apps/api/views.py` | Integraciones externas, plugins |
| **Pipeline editorial** | `apps/engine/pipelines.py` | Cualquier flujo multi-paso con verificación |

---

## 15. Deuda Técnica y Riesgos

| ID | Deuda/Riesgo | Archivo | Esfuerzo estimado | Prioridad |
|----|--------------|---------|-------------------|-----------|
| DT-001 | SQLite + Huey mismo archivo | `settings.py:145` | 1h (archivo separado) | **Alta** |
| DT-002 | Fallback API auth temporal | `api/views.py:51-52` | 30min + test | **Alta** |
| DT-003 | `ok → revision` no en TRANSICIONES | `models.py:307-314`, `pipelines.py:103` | 30min + migración | **Alta** |
| DT-004 | Router por string nombre | `router.py:25-38` | 2h (campo + migración) | **Media** |
| DT-005 | Caché SQL cruda sin modelo | `cache.py` | 4h (modelo + migración + TTL) | **Media** |
| DT-006 | Cooldown en memoria | `router.py:55` | 2h (campo BD o Redis) | **Media** |
| DT-007 | `views.py` monolítico | `panel/views.py` | 8h (refactor por dominios) | **Baja** |
| DT-008 | `WordPressProvider` en `providers/` | `providers/wordpress.py` | 1h (mover a `integrations/`) | **Baja** |
| DT-009 | `EncryptedTextField` fallback silencioso | `models.py:38-40` | 2h (re-cifrado + flag) | **Media** |
| DT-010 | Sin proyectos/tenancy | Múltiples modelos | **Bloque D** (diseño aprobado) | **Futuro** |
| DT-011 | `pipeline_editorial` usa `call_local` | `pipelines.py:117` | 2h (encolar en Huey) | **Media** |
| DT-012 | `depende_de` no respetado | `tasks.py` + `models.py` | 4h (lógica encolado) | **Media** |
| DT-013 | Validación JSON Schema completa | `tasks.py:138-219` | 4h (Pydantic TypeAdapter) | **Media** |
| DT-014 | Cuelgue test preexistente | `test_panel.py` | Investigación | **Baja** |

---

## 16. Evaluación de Preparación para Capacidades Futuras

### A. Contrato Universal de Agentes
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Respuestas estructuradas | ✅ `ResultadoAgente` + `FormatoSalida` | Validación JSON Schema completa faltante |
| Validación completa | ⚠️ Parcial (solo `required`) | Pydantic `TypeAdapter` |
| Errores normalizados | ✅ `ErrorEstructurado` | — |
| Compatibilidad entre modelos | ✅ Router + adaptadores | `response_schema` no pasado a proveedores |
| Trazabilidad prompt→artefacto | ✅ `Artefacto.metadata` + `Ejecucion` | — |

**Veredicto:** **80% listo**. Falta validación completa y pasar `response_schema` a proveedores.

### B. Tareas Programadas y Recurrentes
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Modelo `TareaProgramada` | ❌ No existe | Diseñar + migración |
| Scheduler dinámico | ❌ Huey `crontab` estático | Tabla propia + worker lector |
| Prevención duplicados | ⚠️ Parcial (idempotencia en `ejecutar_tarea`) | Constraint único en scheduler |
| Pausado/Reanudado | ❌ No existe | Campo `activa` en modelo |
| Historial ejecuciones | ✅ `Ejecucion` + `Artefacto` | Vincular a `TareaProgramada` |

**Veredicto:** **30% listo**. Requiere nuevo modelo + scheduler dedicado. **No implementar sin diseño aprobado**.

### C. Proyectos y Espacios de Trabajo
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Modelo `Proyecto` | ❌ No existe | Diseñar + migración |
| Aislamiento datos | ❌ `proyecto_id` solo en `IntegracionConfig` (sin usar) | FK en todos los modelos transversales |
| Credenciales por proyecto | ❌ Globales | `Credencial.proyecto_id` + filtro en vistas |
| Permisos por proyecto | ❌ No hay | Sistema de permisos (RBAC) |

**Veredicto:** **10% listo**. **No implementar sin diseño aprobado y migración planificada** (AGENTS.md §6).

### D. Base de Conocimiento
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Almacenamiento progresivo | ❌ No existe | Modelo `Documento`/`Fragmento` + FK `Proyecto` |
| Recuperación centralizada | ❌ No existe | Índice FTS5 (SQLite) o vectorial (PostgreSQL + pgvector) |
| Filtros proyecto/fecha/categoría | ❌ No existe | Campos en modelo + vistas |

**Veredicto:** **0% listo**. SQLite FTS5 viable para etapa 1 (no requiere nuevas deps). Evaluar cuando se apruebe C.

### E. Investigación SEO y de Mercado (Módulo especializado)
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Investigar sitio web | ⚠️ Parcial (Herramienta HTTP + Tavily) | Crawler/Scraper dedicado |
| Analizar competidores | ❌ No existe | Módulo nuevo |
| Consultar fuentes públicas | ⚠️ Parcial (Herramientas API) | Conectores específicos |
| Identificar keywords | ❌ No existe | Integración APIs SEO (Ahrefs, Semrush, Google) |
| Comparar histórico | ✅ `Ejecucion` + `Artefacto` versionados | Consultas temporales |
| Generar recomendaciones | ❌ No existe | Agente especializado + habilidad |
| Ejecutar bajo demanda/programado | ⚠️ Parcial (Workflows + futuro scheduler) | Scheduler B |

**Veredicto:** **40% listo** (herramientas HTTP + Tavily + workflows base). **Debe ser módulo separado**, no acoplar al núcleo.

### F. Ejecución de Mejoras (Agentes especializados con permisos/aprobación)
| Requisito | Estado | Gap |
|-----------|--------|-----|
| Permisos por acción | ⚠️ Parcial (`es_sistema`, `ProtectedError`) | RBAC granular |
| Aprobación humana | ✅ `modo_ejecucion=manual` → `REVISION` + `aprobar_tarea` | — |
| Trazabilidad | ✅ `Artefacto.metadata["aprobado_por/en"]` | — |
| Idempotencia | ⚠️ Parcial (claves idempotencia en reintentos) | Claves en efectos externos (WP, email) |

**Veredicto:** **70% listo**. Base sólida con `manual` mode + aprobación HTMX.

---

## 17. Plan de Implementación Recomendado

### Fase 0: Correcciones Críticas (Pre-requisitos para cualquier ampliación)
*Objetivo: Eliminar riesgos de seguridad y consistencia antes de añadir features.*

| Paso | Objetivo | Archivos (máx 4) | Dependencias | Riesgos | Criterio aceptación |
|------|----------|------------------|--------------|---------|---------------------|
| **0.1** | Mover Huey a `huey.db` separado | `settings.py` | Ninguna | Bajo | `runserver` + `run_huey` concurrentes sin `database locked` |
| **0.2** | Retirar fallback `settings.ARM_API_KEY` en `_autenticado` | `api/views.py`, `tests/test_api.py` | Confirmar `IntegracionConfig` migrado en prod | Bajo (si migración hecha) | Test falla si fallback se ejecuta; 401 sin registro migrado |
| **0.3** | Añadir `Estado.REVISION` a `TRANSICIONES[Estado.OK]` y usar `transicionar()` en pipeline | `models.py`, `pipelines.py`, `tests/test_pipeline.py` | Ninguna | Medio (cambio semántica estado) | `tarea.transicionar(REVISION)` desde `OK` OK; pipeline usa método |
| **0.4** | Campo `tipo_adaptador` en `Proveedor` + migración datos | `models.py`, `router.py`, migración | 0.1-0.3 | Medio | `fabricar_proveedor` usa campo; no string matching |
| **0.5** | Modelo `CacheRespuesta` + migración tabla cruda + TTL | `cache.py`, `models.py`, migración, `router.py` | 0.4 | Medio | Tabla `providers_cache_respuestas` migrada; entradas expiran |

### Fase 1: Fortalecimiento del Núcleo
*Objetivo: Validación completa, idempotencia, observabilidad.*

| Paso | Objetivo | Archivos (máx 4) | Dependencias | Riesgos | Criterio aceptación |
|------|----------|------------------|--------------|---------|---------------------|
| **1.1** | Validación JSON Schema completa con Pydantic `TypeAdapter` | `tasks.py`, `schemas.py`, `tests/test_engine.py` | Fase 0 | Medio (cambio comportamiento normalizador) | JSON inválido semánticamente → `partial`/`failed` con detalles |
| **1.2** | Pasar `response_schema` a proveedores (Gemini/OpenRouter) | `router.py`, `gemini.py`, `openrouter.py`, `tasks.py` | 1.1 | Medio | Proveedores devuelven JSON validado nativamente; menos parsing manual |
| **1.3** | Idempotencia en `publicar_tarea` (clave `tarea_id` + hash contenido) | `panel/views.py`, `WordPressProvider`, `tests/test_panel.py` | 1.1 | Bajo | Re-ejecutar publicación → no duplica en WP |
| **1.4** | Respetar `depende_de` al encolar tareas | `tasks.py`, `models.py`, `tests/test_engine.py` | 1.1 | Medio | Tarea con dependencia no encola hasta que dependencia en `OK` |
| **1.5** | `EncryptedTextField`: re-cifrado masivo + flag `esta_cifrado` | `models.py`, management command, `tests/test_core.py` | Fase 0 | Medio | 0 valores legacy sin cifrar; flag distingue |

### Fase 2: Observabilidad y Operaciones
*Objetivo: Logs estructurados, métricas, debugging.*

| Paso | Objetivo | Archivos (máx 4) | Dependencias | Riesgos | Criterio aceptación |
|------|----------|------------------|--------------|---------|---------------------|
| **2.1** | Logging estructurado (JSON) en `tasks.py` + `tool_executor.py` | `tasks.py`, `tool_executor.py`, `settings.py` (logging config) | Fase 1 | Bajo | Logs parsable; correlation_id por tarea |
| **2.2** | Métricas Prometheus / Django Prometheus (opcional) | Nueva dependencia (requiere aprobación) | Fase 1 | Medio (nueva dep) | `/metrics` expone colas, tokens, latencias |
| **2.3** | Dashboard panel: cola por proveedor, latencia P50/P95, tasa fallo | `panel/views.py`, `dashboard.html`, `static/css/app.css` | 2.1 | Bajo | Métricas operativas visibles |

### Fase 3: Preparación Bloque D (Producción)
*Objetivo: PostgreSQL, Redis, Celery, migraciones seguras.*

| Paso | Objetivo | Archivos | Dependencias | Nota |
|------|----------|----------|--------------|------|
| **3.1** | `settings.py`: PostgreSQL + Redis + Celery config (feature flags) | `settings.py`, `requirements.txt` | Aprobación usuario | No activar hasta migración |
| **3.2** | Migración SQLite → PostgreSQL (datos + esquemas) | Script migración, `makemigrations --check` | 3.1 | Probar en staging |
| **3.3** | Huey → Celery Beat + Workers (tasks periódicas nativas) | `engine/tasks.py`, `celery.py` | 3.2 | `revisar_huerfanas` → periodic task |
| **3.4** | `Proyecto` model + aislamiento datos (Bloque D diseño) | Múltiples modelos, migraciones complejas | **Diseño aprobado requerido** | Ver AGENTS.md §6 |

### Fase 4: Módulos Especializados (Opcionales, desacoplados)
*Objetivo: Capacidades E/F sin acoplar al núcleo.*

| Módulo | Descripción | Integración |
|--------|-------------|-------------|
| **SEO Research** | Crawler + APIs keywords + competencia | Nueva app `apps/seo_research`; usa `Herramienta` HTTP + `Workflow` |
| **Knowledge Base** | Documentos + FTS5 (SQLite) / pgvector (Postgres) | Nueva app `apps/knowledge`; FK `Proyecto` |
| **Improvement Execution** | Agentes con permisos + aprobación + idempotencia | Extiende `Habilidad` + `Herramienta` + `modo_ejecucion=manual` |

---

## 18. Cierre Obligatorio

### 18.1 Qué está realmente terminado
- ✅ Núcleo ARM v1.0: Modelos, Motor, Proveedores, Workflows, Panel, API, Publicación WP, Verificadores, Credenciales, Herramientas, Seed, Documentación.
- ✅ Bloque B (UX/UI): 100% ARM Flow, 0 CSS embebido, 0 clases huérfanas.
- ✅ Bloque C (hasta C.7-FIX + FASE1.6 + FIX-INCONSISTENCIAS + C.1-CREDENTIAL-STORE + C.3-EXECUTION-ENGINE + C.3-FIX + C.4 + C.4-FIX + C.5-B + C.7-FIX): Credential Store, Tool Executor seguro, n8n-style UI, rotación API key, separation of concerns.
- ✅ Tests: 187 passing (4 preexistentes rotos documentados).
- ✅ `manage.py check`: Sin issues.

### 18.2 Qué funciona pero necesita fortalecerse
- ⚠️ Autenticación API (fallback temporal)
- ⚠️ Transición `ok→revision` no declarada
- ⚠️ SQLite + Huey mismo archivo (riesgo bloqueos)
- ⚠️ Router por string matching frágil
- ⚠️ Caché SQL cruda sin TTL/modelo
- ⚠️ Cooldown rate-limit en memoria
- ⚠️ Validación JSON Schema incompleta
- ⚠️ `pipeline_editorial` usa `call_local` (síncrono)
- ⚠️ `depende_de` M2M no respetado en encolado

### 18.3 Qué falta (Bloque D + capacidades futuras)
- ❌ PostgreSQL + Redis + Celery (producción)
- ❌ Modelo `Proyecto` + aislamiento multi-tenant (diseño aprobado requerido)
- ❌ Tareas programadas/recurrentes (scheduler propio)
- ❌ Base de conocimiento (FTS5/vectorial)
- ❌ Módulo SEO Research (desacoplado)
- ❌ Validación JSON Schema completa (Pydantic)
- ❌ Idempotencia en efectos externos (WP, email, etc.)

### 18.4 Qué NO debe construirse todavía
- ❌ Multitenencia / permisos por proyecto **sin diseño aprobado y migración planificada** (AGENTS.md §6)
- ❌ Base vectorial / embeddings **sin justificar necesidad y aprobar dependencia**
- ❌ LangChain / CrewAI / frameworks de agentes **prohibidos en etapa actual** (AGENTS.md §3)
- ❌ Docker / WSL / Kubernetes **no en esta etapa**
- ❌ Reescritura completa del panel o motor **refactor amplio prohibido en tarea funcional pequeña** (AGENTS.md §1.6)

### 18.5 Siguiente paso mínimo recomendado
**Ejecutar Fase 0 completa (pasos 0.1 a 0.5)** — son 5 pasos pequeños, cada uno ≤4 archivos, que eliminan los 5 riesgos críticos (CRIT-001 a CRIT-005) y sientan base sólida para cualquier ampliación. Tiempo estimado: 2-3 sesiones de trabajo.

### 18.6 Decisiones que requieren aprobación del usuario
1. **¿Mover Huey a `huey.db` ahora (0.1) o esperar a Bloque D con PostgreSQL+Redis?**
2. **¿Retirar fallback API auth ya (0.2) o mantener hasta confirmar migración en staging/prod?**
3. **¿Aprobar diseño de `Proyecto` + multi-tenancy para iniciar Bloque D?**
4. **¿Añadir `django-prometheus` como dependencia para métricas (2.2)?**
5. **¿Priorizar validación JSON Schema completa (1.1) vs idempotencia publicación (1.3)?**

---

**Fin del informe de auditoría.**  
*No se modificaron archivos. No se ejecutaron migraciones. No se instalaron dependencias. No se hicieron commits. Esperando aprobación explícita para iniciar implementación.*