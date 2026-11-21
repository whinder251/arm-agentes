> **Nota**: Este documento describe el estado del proyecto en noviembre 2026 (pasos 0-23). Para el estado actual, consulta docs/plan.md.

# Roadmap de ARM â€” Estado Actual (2026-11-14)

## Pasos Completados (0-23)

ARM es un orquestador de agentes de IA self-hosted con:

- Panel web estilo Apple/SaaS con dashboard de mÃ©tricas
- CreaciÃ³n de tareas con asignaciÃ³n automÃ¡tica de agente
- Workflows multi-paso con equipos de agentes y orquestaciÃ³n automÃ¡tica
- API REST para integraciones externas (Pydantic v2, autenticaciÃ³n por header)
- PublicaciÃ³n directa en WordPress (como borrador)
- Cifrado de API keys con cryptography.fernet
- ValidaciÃ³n de cuotas de tokens en tiempo real
- Verificadores deterministas de SEO, estilo y hechos
- Vista de integraciones con API key visible

## PrÃ³ximos pasos (fuera del nÃºcleo Django)

- Plugin de WordPress (repo paralelo en PHP) que consuma la API de ARM
- Visualizador de pipeline tipo n8n (opcional, requiere React/Vue)
- IntegraciÃ³n con Telegram (webhook simple)
- GeneraciÃ³n de imÃ¡genes (nueva habilidad con proveedor de imÃ¡genes)

## Dependencias tÃ©cnicas

- Django 5.2 LTS, Huey, SQLite (modo WAL), Pydantic v2, cryptography
- Sin Docker, sin Redis, sin Celery, sin Postgres
