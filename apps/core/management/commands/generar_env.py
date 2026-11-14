"""Comando de gestión para generar claves de entorno y preparar .env.

Genera SECRET_KEY y ARM_ENCRYPTION_KEY válidas y las escribe en un archivo
.env local si este no existe. NO re-cifra automáticamente las api_key ya
almacenadas en la base de datos, para evitar corrupción silenciosa. Al
finalizar, imprime un aviso de que el usuario debe volver a ingresar las
API Keys de sus proveedores en el panel de Configuración.
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key
from cryptography.fernet import Fernet


class Command(BaseCommand):
    help = "Genera SECRET_KEY y ARM_ENCRYPTION_KEY y las escribe en .env si no existe."

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        env_path = base_dir / ".env"

        secret_key = get_random_secret_key()
        encryption_key = Fernet.generate_key().decode()

        if not env_path.exists():
            env_path.write_text(
                f"SECRET_KEY={secret_key}\n"
                f"ARM_ENCRYPTION_KEY={encryption_key}\n"
                f"ARM_API_KEY=dev-api-key-123\n"
                f"DEBUG=True\n",
                encoding="utf-8",
            )
            self.stdout.write(
                self.style.SUCCESS(f".env creado en {env_path}")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f".env ya existe en {env_path}; no se sobrescribe.")
            )

        self.stdout.write("")
        self.stdout.write("Claves generadas (copie manualmente si lo prefiere):")
        self.stdout.write(f"  SECRET_KEY={secret_key}")
        self.stdout.write(f"  ARM_ENCRYPTION_KEY={encryption_key}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "AVISO: las api_key de proveedores ya almacenadas pudieron haberse "
                "guardado en texto plano o estar corruptas. Vuelva a ingresarlas en el "
                "panel de Configuración tras definir ARM_ENCRYPTION_KEY en el .env."
            )
        )
