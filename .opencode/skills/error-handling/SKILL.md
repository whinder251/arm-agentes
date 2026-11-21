---
name: error-handling
description: Manejo de errores y observabilidad en ARM Agentes (logging por módulo, niveles, contexto trazable, mensajes al usuario, excepciones específicas y tareas Huey). Úsala al escribir o revisar try/except, logging, mensajes de error en vistas, llamadas externas o tareas en segundo plano.
---

# Skill: Error Handling & Observability

## Contexto
Sistema distribuido con worker Huey, vistas web y llamadas externas. Los errores deben ser trazables sin exponer detalles sensibles.

## Reglas Estrictas
- **Logger por Módulo**: Cada archivo usa `logger = logging.getLogger(__name__)`. No usar `print()` ni `logging.getLogger()` genérico.
- **Niveles de Log**:
  - `DEBUG`: Flujo normal detallado (ej. "Iniciando extracción de URL X")
  - `INFO`: Eventos de negocio importantes (ej. "Hallazgo creado: {titulo}")
  - `WARNING`: Fallos recuperables (ej. "Timeout en URL X, se reintentará")
  - `ERROR`: Fallos que requieren atención (ej. "Fallo en extracción de contenido tras 3 intentos")
- **Contexto en Logs**: Incluir siempre identificadores trazables: `investigacion_id`, `hallazgo_id`, `url`. Nunca loguear el contenido completo de respuestas HTTP.
- **Feedback al Usuario**: En vistas, usar `messages.error(request, "Ocurrió un error al procesar la solicitud.")` sin detalles técnicos. Los detalles van al log.
- **Excepciones Específicas**: Capturar excepciones concretas (`requests.RequestException`, `ValidationError`), nunca `except Exception:` salvo en el nivel más externo (ver Worker Huey).

## Worker Huey
Una tarea que falla no debe dejar el fallo sin rastro. Patrón:

- Dentro de la tarea, capturar excepciones **específicas** y registrarlas con contexto.
- El **único** `except Exception:` permitido es el más externo de la tarea, y siempre registra el traceback con `logger.exception(...)` (o `logger.error(..., exc_info=True)`).
- Decidir de forma explícita qué ocurre después:
  - **Fallo recuperable** (timeout, 5xx): registrar con `WARNING` y volver a lanzar (`raise`) para que Huey aplique `retries`. Si se captura y no se relanza, Huey no reintenta.
  - **Fallo definitivo**: registrar con `ERROR`, dejar el objeto en estado de error (ej. `estado='fallida'`) y terminar la tarea con normalidad.

```python
logger = logging.getLogger(__name__)

@db_task(retries=3, retry_delay=30)
def procesar_investigacion(investigacion_id):
    try:
        ejecutar_investigacion(investigacion_id)
    except requests.RequestException:
        logger.warning("Fallo de red, se reintentará", extra={"investigacion_id": investigacion_id}, exc_info=True)
        raise  # Huey reintenta
    except Exception:
        logger.exception("Fallo inesperado en investigación %s", investigacion_id)
        marcar_como_fallida(investigacion_id)
```
