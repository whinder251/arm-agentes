"""Data migration: migra filas de la tabla cruda providers_cache_respuestas
a CacheRespuesta y elimina la tabla cruda."""

from __future__ import annotations

import json
from datetime import timedelta

from django.db import migrations, connection
from django.utils import timezone

TABLA_CRUDA = "providers_cache_respuestas"


def migrar_cache_existente(apps, schema_editor):
    """Lee la tabla cruda si existe, crea entradas CacheRespuesta y la elimina."""
    CacheRespuesta = apps.get_model("core", "CacheRespuesta")
    with connection.cursor() as cursor:
        tablas = connection.introspection.table_names(cursor)
        if TABLA_CRUDA not in tablas:
            return
        cursor.execute(
            f"SELECT clave, modelo, texto, tokens_in, tokens_out, crudo, creada "
            f"FROM {TABLA_CRUDA}"
        )
        filas = cursor.fetchall()

    for fila in filas:
        clave, modelo, texto, tokens_in, tokens_out, crudo, creada = fila
        try:
            creada_dt = timezone.datetime.fromisoformat(creada)
        except (ValueError, TypeError, AttributeError):
            creada_dt = timezone.now()
        if timezone.is_naive(creada_dt):
            creada_dt = timezone.make_aware(creada_dt)
        expira = creada_dt + timedelta(days=30)
        crudo_parseado = None
        if crudo not in (None, ""):
            try:
                crudo_parseado = json.loads(crudo)
            except (ValueError, TypeError):
                crudo_parseado = None
        CacheRespuesta.objects.update_or_create(
            clave=clave,
            defaults={
                "modelo": modelo,
                "texto": texto,
                "tokens_in": tokens_in or 0,
                "tokens_out": tokens_out or 0,
                "crudo": crudo_parseado,
                "creada": creada_dt,
                "expira": expira,
            },
        )

    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {TABLA_CRUDA}")


def no_op(apps, schema_editor):
    """Reverse no-op: es caché, no es crítico recuperar."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_cacherespuesta"),
    ]

    operations = [
        migrations.RunPython(migrar_cache_existente, no_op),
    ]
