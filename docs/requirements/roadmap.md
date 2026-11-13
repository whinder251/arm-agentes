# Roadmap de ARM — Estado Actual (2026-11-14)

## Pasos Completados (0-23)

ARM es un orquestador de agentes de IA self-hosted con:

- Panel web estilo Apple/SaaS con dashboard de métricas
- Creación de tareas con asignación automática de agente
- Workflows multi-paso con equipos de agentes y orquestación automática
- API REST para integraciones externas (Pydantic v2, autenticación por header)
- Publicación directa en WordPress (como borrador)
- Cifrado de API keys con cryptography.fernet
- Validación de cuotas de tokens en tiempo real
- Verificadores deterministas de SEO, estilo y hechos
- Vista de integraciones con API key visible

## Próximos pasos (fuera del núcleo Django)

- Plugin de WordPress (repo paralelo en PHP) que consuma la API de ARM
- Visualizador de pipeline tipo n8n (opcional, requiere React/Vue)
- Integración con Telegram (webhook simple)
- Generación de imágenes (nueva habilidad con proveedor de imágenes)

## Dependencias técnicas

- Django 5.2 LTS, Huey, SQLite (modo WAL), Pydantic v2, cryptography
- Sin Docker, sin Redis, sin Celery, sin Postgres