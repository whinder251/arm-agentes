---
name: ai-llm-integration
description: Reglas para integrar modelos de lenguaje (LLM) en ARM Agentes (rate limits, reintentos, fallback entre proveedores, conteo de tokens, validación de respuestas, secretos, timeouts y costos). Úsala al escribir o modificar código que llame a proveedores LLM, agentes o generación de contenido con IA.
---

# Skill: AI/LLM Integration

## Contexto
ARM consume modelos de lenguaje para analizar hallazgos y generar contenido. Las llamadas son costosas (tokens, tiempo, rate limits).

## Reglas Estrictas
- **Rate Limits**: Respetar siempre el `limite_rpm` del proveedor. Implementar backoff exponencial con jitter en reintentos (máximo 3 intentos).
- **Fallback de Proveedores**: Si el proveedor primario falla con error 5xx o timeout, intentar el proveedor secundario configurado. No hacer fallback en errores 4xx (credenciales inválidas, cuota agotada).
  - Excepción: `429 Too Many Requests` es un límite temporal, no un error de credenciales. Reintentar con backoff respetando `Retry-After`; solo pasar al secundario si se agotan los reintentos.
- **Conteo de Tokens**: Registrar tokens de entrada y salida en cada llamada. Actualizar la cuota del proveedor de forma atómica (`F()`).
- **Validación de Respuestas**: Antes de guardar la salida del modelo, validar que no esté vacía, que tenga la estructura esperada (JSON si aplica), y que no contenga alucinaciones obvias (texto repetitivo, markers de "como modelo de IA").
- **Secretos**: NUNCA incluir API keys, system prompts completos o datos de usuarios en logs de error. Loguear solo el ID de la llamada y el tipo de error.
- **Timeouts**: Toda llamada a un LLM debe tener timeout explícito (máximo 60s para generación, 10s para embeddings).
- **Costos**: Preferir modelos pequeños para tareas simples (clasificación, extracción de título) y modelos grandes solo para generación de contenido.
