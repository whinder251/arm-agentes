from django.contrib import admin

from .models import Agente, Habilidad, ModeloLLM, Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "base_url", "rpm", "limite_diario")
    search_fields = ("nombre",)


@admin.register(ModeloLLM)
class ModeloLLMAdmin(admin.ModelAdmin):
    list_display = ("model_id", "proveedor", "prioridad", "json_nativo", "activo")
    list_filter = ("activo", "json_nativo", "proveedor")
    search_fields = ("model_id",)


@admin.register(Habilidad)
class HabilidadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug")
    search_fields = ("nombre", "slug")


@admin.register(Agente)
class AgenteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "modelo", "temperatura")
    list_filter = ("modelo",)
    filter_horizontal = ("habilidades",)
