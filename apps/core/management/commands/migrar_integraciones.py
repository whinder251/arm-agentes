"""Comando de gestión idempotente para migrar ARM_API_KEY a IntegracionConfig.

Lee ARM_API_KEY del entorno, calcula su hash SHA-256 y crea el registro
IntegracionConfig (tipo='arm_api', activa=True) si aún no existe.
No genera claves nuevas ni imprime el secreto en consola.
"""

import hashlib
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.models import IntegracionConfig


class Command(BaseCommand):
    help = (
        "Migra ARM_API_KEY del entorno a IntegracionConfig como hash SHA-256 "
        "(idempotente: no duplica si ya existe)."
    )

    def handle(self, *args, **options):
        clave = os.environ.get("ARM_API_KEY") or getattr(
            settings, "ARM_API_KEY", None
        )
        if not clave:
            self.stdout.write(
                self.style.ERROR(
                    "ARM_API_KEY no está definida en el entorno ni en settings."
                )
            )
            return

        if IntegracionConfig.objects.filter(
            tipo="arm_api", activa=True
        ).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Ya existe una IntegracionConfig activa de tipo arm_api. "
                    "No se hace nada (idempotente)."
                )
            )
            return

        hash_clave = hashlib.sha256(clave.encode("utf-8")).hexdigest()
        IntegracionConfig.objects.create(
            nombre="ARM API",
            tipo="arm_api",
            credenciales=hash_clave,
            activa=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "IntegracionConfig arm_api creada a partir de ARM_API_KEY del entorno."
            )
        )
