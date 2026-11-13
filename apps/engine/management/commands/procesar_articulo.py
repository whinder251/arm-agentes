"""Comando para procesar un artículo con el pipeline editorial."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.core.models import Habilidad, Tarea
from apps.engine.pipelines import pipeline_editorial


def _familia(regla: str) -> str:
    if regla.startswith("SEO"):
        return "SEO"
    if regla.startswith("FCT"):
        return "Hechos"
    return "Estilo"


class Command(BaseCommand):
    help = "Reescribe un artículo, lo optimiza para SEO y muestra el informe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo", required=True, help="Ruta del archivo de texto."
        )
        parser.add_argument(
            "--keyword", required=True, help="Keyword principal del artículo."
        )

    def handle(self, *args, **options):
        ruta = Path(options["archivo"]).expanduser()
        if not ruta.is_file():
            raise CommandError(f"No existe el archivo: {ruta}")

        try:
            texto = ruta.read_text(encoding="utf-8")
        except OSError as error:
            raise CommandError(f"No se pudo leer {ruta}: {error}") from error
        if not texto.strip():
            raise CommandError("El archivo está vacío.")

        keyword = options["keyword"].strip()
        if not keyword:
            raise CommandError("La keyword no puede estar vacía.")

        habilidad = Habilidad.objects.filter(slug="reescritura").first()
        if habilidad is None:
            raise CommandError("Falta la habilidad con slug 'reescritura'.")

        tarea = Tarea.objects.create(
            habilidad=habilidad,
            payload={"texto": texto, "keyword": keyword},
        )
        resultado = pipeline_editorial(tarea.pk)
        tarea.refresh_from_db()

        self.stdout.write(
            f"Estado final: {tarea.get_estado_display()} ({tarea.estado})"
        )
        url = reverse("admin:core_tarea_change", args=[tarea.pk])
        self.stdout.write(
            f"Revisar en el admin: http://127.0.0.1:8000{url}"
        )

        problemas = resultado.get("problemas", [])
        if resultado.get("resultado") != "ok":
            self.stdout.write(
                f"El pipeline no terminó correctamente: "
                f"{resultado.get('resultado')}."
            )
            return
        if not problemas:
            self.stdout.write("Sin problemas de verificación.")
            return

        self.stdout.write(f"Problemas encontrados: {len(problemas)}")
        for problema in problemas:
            regla = str(problema.get("regla", ""))
            self.stdout.write(
                f"- [{_familia(regla)}] {regla} "
                f"({problema.get('severidad')}): {problema.get('mensaje')}"
            )
