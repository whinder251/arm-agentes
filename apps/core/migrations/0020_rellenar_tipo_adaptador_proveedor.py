from django.db import migrations


def rellenar_tipo_adaptador(apps, schema_editor):
    Proveedor = apps.get_model("core", "Proveedor")
    for proveedor in Proveedor.objects.all():
        nombre = (proveedor.nombre or "").lower()
        if "gemini" in nombre:
            proveedor.tipo_adaptador = "gemini"
        elif "openrouter" in nombre:
            proveedor.tipo_adaptador = "openrouter"
        else:
            proveedor.tipo_adaptador = "custom"
        proveedor.save(update_fields=["tipo_adaptador"])


def no_op(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_proveedor_tipo_adaptador"),
    ]

    operations = [
        migrations.RunPython(rellenar_tipo_adaptador, no_op),
    ]
