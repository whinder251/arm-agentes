"""Crear FormatoSalida y Herramienta, migrar esquemas de Habilidad a FormatoSalida,
y añadir relaciones formato_salida/herramientas a Agente y Tarea."""

from django.db import migrations, models
import django.db.models.deletion


def migrar_esquemas_a_formatosalida(apps, schema_editor):
    """Crea FormatoSalida a partir de Habilidad.esquema_salida y lo asigna
    a los Agente que usan esa habilidad."""
    Habilidad = apps.get_model("core", "Habilidad")
    FormatoSalida = apps.get_model("core", "FormatoSalida")
    Agente = apps.get_model("core", "Agente")

    for habilidad in Habilidad.objects.all():
        esquema = habilidad.esquema_salida
        if not esquema or not isinstance(esquema, dict) or not esquema:
            continue

        # Crear FormatoSalida basado en el esquema de la habilidad
        formato, creado = FormatoSalida.objects.get_or_create(
            slug=f"{habilidad.slug}-formato",
            defaults={
                "nombre": f"{habilidad.nombre} Formato",
                "descripcion": f"Formato migrado de la habilidad '{habilidad.nombre}'.",
                "esquema": esquema,
                "version": habilidad.esquema_version or "v1",
                "permite_parcial": habilidad.permite_parcial,
                "plantilla_formato": "",
            },
        )

        # Asignar el formato a los agentes que tienen esta habilidad
        if creado:
            for agente in habilidad.agentes.all():
                if not agente.formato_salida_id:
                    agente.formato_salida = formato
                    agente.save(update_fields=["formato_salida"])


def no_op(apps, schema_editor):
    """No-op para reversión (los datos se pierden, lo cual es aceptable en este paso)."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_alter_tarea_estado"),
    ]

    operations = [
        # 1) Crear modelo FormatoSalida
        migrations.CreateModel(
            name="FormatoSalida",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("esquema", models.JSONField(default=dict)),
                ("version", models.CharField(default="v1", max_length=20)),
                (
                    "permite_parcial",
                    models.BooleanField(default=False),
                ),
                (
                    "plantilla_formato",
                    models.TextField(
                        blank=True,
                        help_text="Plantilla de ejemplo JSON que se inyecta en el prompt del modelo.",
                    ),
                ),
            ],
            options={
                "verbose_name": "formato de salida",
                "verbose_name_plural": "formatos de salida",
                "ordering": ["nombre"],
            },
        ),
        # 2) Crear modelo Herramienta
        migrations.CreateModel(
            name="Herramienta",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=100)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("scraping", "Scraping web"),
                            ("busqueda", "Búsqueda web"),
                            ("database", "Consulta a base de datos"),
                            ("api", "API externa"),
                            ("python", "Código Python sandbox"),
                        ],
                    ),
                ),
                ("descripcion", models.TextField(blank=True)),
                ("configuracion", models.JSONField(default=dict)),
            ],
            options={
                "verbose_name": "herramienta",
                "verbose_name_plural": "herramientas",
                "ordering": ["nombre"],
            },
        ),
        # 3) Añadir formato_salida a Agente (FK, nullable)
        migrations.AddField(
            model_name="agente",
            name="formato_salida",
            field=models.ForeignKey(
                blank=True,
                help_text="Formato de salida por defecto para este agente.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="agentes",
                to="core.formatosalida",
            ),
        ),
        # 4) Añadir herramientas a Agente (M2M)
        migrations.AddField(
            model_name="agente",
            name="herramientas",
            field=models.ManyToManyField(
                blank=True,
                help_text="Herramientas externas disponibles para este agente.",
                related_name="agentes",
                to="core.herramienta",
            ),
        ),
        # 5) Añadir formato_salida a Tarea (FK, nullable, override opcional)
        migrations.AddField(
            model_name="tarea",
            name="formato_salida",
            field=models.ForeignKey(
                blank=True,
                help_text="Formato de salida override para esta tarea (si no, se usa el del agente).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tareas",
                to="core.formatosalida",
            ),
        ),
        # 6) Migración de datos: esquema_salida -> FormatoSalida, asignar a Agentes
        migrations.RunPython(
            migrar_esquemas_a_formatosalida,
            reverse_code=no_op,
        ),
        # 7) Eliminar campos antiguos de esquema de Habilidad
        migrations.RemoveField(
            model_name="habilidad",
            name="esquema_salida",
        ),
        migrations.RemoveField(
            model_name="habilidad",
            name="esquema_version",
        ),
        migrations.RemoveField(
            model_name="habilidad",
            name="permite_parcial",
        ),
        # 8) Renombrar plantilla_prompt -> instrucciones
        migrations.RenameField(
            model_name="habilidad",
            old_name="plantilla_prompt",
            new_name="instrucciones",
        ),
    ]
