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
