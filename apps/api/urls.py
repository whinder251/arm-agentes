"""Rutas de la API REST para integraciones externas."""

from django.urls import path

from apps.api import views

urlpatterns = [
    path(
        "v1/webhook/tarea/",
        views.webhook_crear_tarea,
        name="api_webhook_tarea",
    ),
    path(
        "v1/tarea/<int:pk>/",
        views.consultar_tarea,
        name="api_consultar_tarea",
    ),
]
