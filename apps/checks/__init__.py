"""Verificadores deterministas de contenido."""

from apps.checks.estilo import verificar_estilo
from apps.checks.seo import verificar_seo

__all__ = ["verificar_estilo", "verificar_seo"]
