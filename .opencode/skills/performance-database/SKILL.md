---
name: performance-database
description: Optimización de rendimiento y base de datos en ARM Agentes (N+1, select_related/prefetch_related, índices, transacciones, F(), paginación, bulk operations, SQLite vs PostgreSQL). Úsala al escribir o revisar queries del ORM, modelos con índices, vistas de listado o procesos por lotes.
---

# Skill: Performance & Database Optimization

## Contexto
Django con SQLite en desarrollo, PostgreSQL en producción. El sistema consulta hallazgos, tareas y ejecuciones frecuentemente.

## Reglas Estrictas
- **N+1 Queries**: Usar `select_related` para ForeignKey (ej. `Hallazgo.objects.select_related('investigacion')`). Usar `prefetch_related` para ManyToMany y reverse ForeignKey.
- **Campos Específicos**: Usar `only('titulo', 'url_articulo')` cuando solo necesitas 2-3 campos de un modelo grande. Usar `defer('contenido_extraido')` para excluir campos de texto largo.
- **Índices**: Añadir `db_index=True` en campos usados en filtros frecuentes: `titulo`, `url_articulo`, `creado_en`, `estado`. Añadir `Index` compuesto para consultas combinadas (ej. `investigacion + creado_en`).
- **Transacciones**: Usar `@transaction.atomic` cuando una operación toca 2+ tablas (ej. crear hallazgo + actualizar contador de investigación).
- **Actualizaciones Atómicas**: Usar `F()` expressions para incrementos (`investigacion.total_hallazgos=F('total_hallazgos')+1`) en lugar de leer-modificar-guardar.
- **Paginación Obligatoria**: Toda vista que liste más de 50 registros debe paginar. Nunca `Model.objects.all()` sin límite en una vista.
- **Bulk Operations**: Usar `bulk_create` y `bulk_update` para operaciones en lote, con `batch_size` de máximo 1000 registros.

## Anti-patrones Prohibidos
- `len(QuerySet)` → usar `.count()`
- `if QuerySet:` → usar `.exists()`
- Iterar un QuerySet grande sin `.iterator()`
- Llamar a `save()` dentro de un loop sin `bulk_update`
- Hacer queries dentro de un loop (usar `in_bulk` o `prefetch_related`)

## Monitoreo de Performance
- En pasos de optimización, usar `django-debug-toolbar` o `connection.queries` para identificar queries lentas.
- Loguear queries que tarden más de 100ms en desarrollo con `DEBUG=True`.
- En producción, revisar logs de PostgreSQL para queries sin índice (`seq_scan`).

## SQLite vs PostgreSQL
- SQLite no soporta concurrencia de escritura. En desarrollo está bien, pero en producción usar PostgreSQL.
- No usar `JSONField` con queries complejas en SQLite (limitado). En PostgreSQL funciona nativo.
- `bulk_create` con `ignore_conflicts=True` funciona en ambos, pero el comportamiento de IDs autoincrementales difiere.
