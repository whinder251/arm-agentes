# ARM - Agent Resource Management

Orquestador de agentes de IA hecho en Django. Corre en local sobre Windows, sin
Docker y sin WSL. La inteligencia viene de APIs externas; este equipo orquesta,
persiste y verifica.

## Entorno
- Windows 11, PowerShell, Python 3.12 dentro de .venv. Equipo con 8 GB de RAM.
- SQLite en modo WAL. Nada de Postgres ni Redis en esta etapa.
- Cola con Huey y SqliteHuey. Nada de Celery ni Celery Beat.
- Dependencias autorizadas: django 5.2 LTS, huey, httpx, pydantic v2,
  python-dotenv, cryptography, pytest, pytest-django, respx.
- Cualquier dependencia nueva necesita justificación escrita y mi aprobación.

## Comandos (PowerShell)
- Activar entorno: .venv\Scripts\Activate.ps1
- Servidor: python manage.py runserver 127.0.0.1:8000
- Worker: python manage.py run_huey
- Tests: python -m pytest -q
- Comprobación: python manage.py check
- Migraciones: python manage.py makemigrations
- Aplicar migraciones: python manage.py migrate

No encadenes comandos con &&. PowerShell 5.1 no lo acepta; usa líneas separadas.

## Reglas de trabajo
1. Un paso por sesión. Máximo 4 archivos por cambio. Si necesitas más, te detienes
   y propones dividirlo en dos pasos.
2. Antes de escribir código entregas un plan de menos de 10 líneas con los archivos
   afectados y el criterio de aceptación. Esperas mi OK.
3. El test se escribe antes o junto al código. Ningún paso cierra sin tests en verde.
4. Los tests nunca llaman a APIs reales. Usa respx con respuestas grabadas en
   tests/fixtures/.
5. Prohibido: docker, docker-compose, WSL, Redis, Celery, Node, npm, LangChain, CrewAI.
6. No inventes firmas ni parámetros de librerías. Si dudas, dilo y pide el enlace
   a la documentación.
7. No leas ni escribas .env. No edites migraciones ya aplicadas. No borres archivos
   sin pedirlo.
8. Entrega diffs mínimos. No reescribas un archivo entero para cambiar una función.
9. Lee solo los archivos que te indico o los que el paso necesite. No explores el
   repositorio completo para orientarte.
10. No lances subagentes salvo que yo lo pida.
11. Si un test sigue fallando tras dos correcciones, detente y explica la causa raíz
    antes de tocar más código.
12. Identificadores en inglés; comentarios, interfaz y documentación en español.
13. Al cerrar el paso, actualiza docs/plan.md con lo hecho y lo pendiente.
14. La ruta del proyecto contiene espacios. Cita siempre las rutas en los comandos
    de PowerShell. Nunca nombres un módulo o paquete Python con espacios.
15. Prohibido marcar un paso como completado en docs/plan.md sin haber ejecutado
    su criterio de aceptación en esta sesión. Pega la salida del comando que lo
    prueba. Si no lo ejecutaste, el estado es pendiente.
16. Para leer archivos usa tu herramienta de lectura, no Get-Content por shell.
    Los comandos de shell quedan para operaciones que esa herramienta no cubre.
17. Escribe el intérprete siempre como .venv\Scripts\python.exe, sin el punto
    y barra iniciales. Las reglas de permisos comparan texto literal.  
    
## Arquitectura
apps/core, apps/agents, apps/providers, apps/engine, apps/checks, apps/panel.

Separación obligatoria:
- Agente: quién ejecuta el trabajo.
- Habilidad: qué sabe hacer, con su esquema de salida.
- Herramienta: qué acciones externas puede ejecutar, con permisos.
- Ejecucion: registro de lo que pasó, con modelo usado y tokens.

La base de datos es la fuente de verdad del estado. La cola solo dispara el trabajo.
Toda salida de modelo se valida con Pydantic antes de guardarse.
La cuota se reserva de forma atómica antes de la llamada, nunca después.

## Verificación
Antes de entregar cualquier paso, ejecuta:
- python -m pytest -q
- python manage.py check

## Definición de terminado
- Tests en verde y sin avisos de Django.
- Migraciones generadas y aplicadas cuando el paso toque modelos.
- docs/plan.md actualizado.
- Resumen de 5 líneas con qué cambió y qué quedó pendiente.

## Referencias
- docs/plan.md: estado del proyecto y criterio de aceptación de cada paso.
- docs/estilo.md: reglas de escritura que aplica apps/checks al contenido generado.


## Reglas de Negocio Aprobadas
- RB-009: Sistema rechaza encolación si excede cuota diaria o RPM del proveedor.
- RB-010: Si modo_ejecucion de habilidad es 'manual', flujo se pausa y genera tarea en revision.
- RB-011: Workflow se ejecuta en orden. Paso N no se encola hasta que Paso N-1 esté en ok.
- RB-013: api_key se cifra antes de guardar en base de datos (usar cryptography).
- RB-014: Límite de tokens diario por proveedor es obligatorio.
- RB-017: Endpoint REST requiere autenticación con token.

## Visión de Largo Plazo
ARM evolucionará de un procesador de tareas simples a un orquestador de flujos de trabajo multi-paso con equipos de agentes, integración con WordPress y API REST para sistemas externos. Ver docs/requirements/roadmap.md.


## Reglas de Diseño UI (estilo Apple / SaaS moderno)

### Paleta
- Fondo principal: #F5F5F7 (gris claro Apple)
- Fondo de tarjetas y superficies: #FFFFFF
- Texto primario: #1D1D1F
- Texto secundario: #6E6E73
- Acento primario: #0071E3 (azul Apple)
- Acento secundario: #34C759 (verde éxito)
- Error / destructivo: #FF3B30
- Bordes sutiles: #D2D2D7

### Tipografía
- Familia: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif
- Títulos: font-weight 600 o 700, letter-spacing -0.02em
- Cuerpo: font-weight 400, line-height 1.5
- Texto pequeño (metadatos): font-size 0.85rem, color #6E6E73

### Formas y bordes
- Border-radius: 12px para tarjetas, 8px para botones e inputs, 6px para badges
- Bordes: 1px solid #D2D2D7 en inputs y tarjetas inactivas
- Sin bordes rectos ni esquinas cuadradas

### Profundidad y elevación
- Sombras suaves: box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)
- Hover en tarjetas: box-shadow: 0 4px 12px rgba(0,0,0,0.1)
- Glassmorphism permitido en barras laterales y modales: backdrop-filter: blur(20px), background: rgba(255,255,255,0.8)

### Layout
- Espaciado generoso: padding 24px en contenedores, gap 16px entre elementos
- Grid simétrico cuando aplique (2 o 3 columnas)
- Sidebar: 260px de ancho, fondo con blur, separador sutil a la derecha
- Mucho espacio en blanco (whitespace) entre secciones

### Componentes
- Botones primarios: fondo #0071E3, texto blanco, border-radius 8px, padding 10px 18px
- Botones secundarios: fondo transparente, borde 1px #D2D2D7, texto #1D1D1F
- Inputs: fondo #FFFFFF, borde 1px #D2D2D7, border-radius 8px, focus con borde #0071E3 y outline none
- Badges de estado: border-radius 12px, padding 4px 10px, font-size 0.75rem, font-weight 500
- Tablas: sin bordes verticales, solo líneas horizontales sutiles #D2D2D7, header con fondo #F5F5F7

### Prohibido
- Fondos crema (#faf5e5) o tonos sepia
- Bordes rectos o esquinas cuadradas
- Sombras duras o con colores saturados
- Gradientes púrpura/azul genéricos de IA
- Emojis como iconos de UI
- Layouts de 3 tarjetas de precios simétricas sin propósito


## Actualización de Estado (2026-11-14)
- Pasos 0-22b completados. Ver `docs/plan.md` para detalles.
- Paso 23 completado: Integraciones y Propagación de Fallos en Workflows.
- Regla añadida: El agente NO debe ejecutar `git push`. El usuario lo hace manualmente.
- Regla añadida: Se autorizan hasta 6 archivos para el Paso 21 combinado (excepción a la regla de 4).