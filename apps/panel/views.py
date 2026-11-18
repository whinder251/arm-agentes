from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django import forms
from django.conf import settings
from django.db import models
from apps.core import defaults
from django.db.models import Sum, ProtectedError
from django.core.paginator import Paginator
from django.forms import inlineformset_factory
from django.http import JsonResponse
import markdown
import secrets
import logging
from pathlib import Path
from dotenv import set_key
from apps.core.models import (
    Tarea, Proveedor, ModeloLLM, Habilidad, FormatoSalida, Herramienta, Agente, Equipo,
    Workflow, PasoWorkflow, Ejecucion, IntegracionConfig, DestinoPublicacion, Credencial,
)
import json
import requests
from apps.engine.tasks import ejecutar_tarea, continuar_workflow
from apps.engine.tool_executor import (
    validar_endpoint_seguro,
    construir_headers_autenticacion,
    _sanitizar_config,
)
from apps.providers.wordpress import WordPressProvider
from apps.panel.forms import (
    AgenteForm,
    CredencialForm,
    DestinoPublicacionForm,
    FormatoSalidaForm,
    HabilidadForm,
    HerramientaForm,
    ModeloLLMForm,
    ProveedorForm,
)

logger = logging.getLogger(__name__)

# ============================================================
# Paso C.5-B: Catálogo de tipos de herramientas (n8n-style)
# ============================================================
TOOL_TYPES = {
    "http_request": {
        "nombre": "HTTP Request",
        "icono": "M3 3h18v18H3z M3 9h18 M9 3v18",
        "descripcion": "Conecta con cualquier API REST o endpoint HTTP.",
        "ayuda_sidebar": "Usa {{secreto}} en cualquier campo para inyectar la API Key de la credencial vinculada. El método DELETE está bloqueado por seguridad; usa Personalizada si lo necesitas.",
        "campos": [
            {"name": "method", "label": "Método", "widget": "select", "choices": ["GET", "POST", "PUT", "PATCH"], "initial": "POST"},
            {"name": "endpoint", "label": "URL o ruta", "widget": "input", "placeholder": "https://api.ejemplo.com/v1/recurso o /recurso"},
            {"name": "timeout", "label": "Timeout (segundos)", "widget": "number", "initial": 30, "min": 1, "max": 120},
            {"name": "body_template", "label": "Cuerpo de la petición (JSON)", "widget": "textarea", "rows": 4, "placeholder": "{\"query\": \"{{texto}}\"}"}
        ]
    },
    "supabase-query": {
        "nombre": "Supabase",
        "icono": "M10 2 L2 7 L10 12 L18 7 L10 2 Z M2 7v10l8 5 M18 7v10l-8 5",
        "descripcion": "Consulta tablas de tu base de datos Supabase.",
        "ayuda_sidebar": "La base_url vive en la credencial, no aquí. Escribe solo el nombre de la tabla o la ruta relativa. La clave anon requiere GRANT SELECT en el SQL Editor de Supabase para leer tablas.",
        "campos": [
            {"name": "endpoint", "label": "Tabla o ruta", "widget": "input", "placeholder": "core_tarea o /rest/v1/posts"},
            {"name": "method", "label": "Método", "widget": "select", "choices": ["GET", "POST", "PATCH", "DELETE"], "initial": "GET"},
            {"name": "timeout", "label": "Timeout (segundos)", "widget": "number", "initial": 30, "min": 1, "max": 120}
        ]
    },
    "google-sheets": {
        "nombre": "Google Sheets",
        "icono": "M4 3h12l4 4v14H4z M16 3v4h4 M8 12h8 M8 16h8",
        "descripcion": "Lee o escribe filas en una hoja de cálculo.",
        "ayuda_sidebar": "El spreadsheet_id es la cadena larga en la URL de tu Google Sheet. La credencial debe ser tipo JSON con el contenido de credentials.json de una Service Account de Google Cloud.",
        "campos": [
            {"name": "spreadsheet_id", "label": "ID de la hoja", "widget": "input", "placeholder": "1BxiMVs0XRA5nFMdKv..."},
            {"name": "sheet_name", "label": "Nombre de la pestaña", "widget": "input", "placeholder": "Hoja 1"},
            {"name": "action", "label": "Acción", "widget": "select", "choices": ["read", "append", "update"], "initial": "read"}
        ]
    },
    "wordpress-connector": {
        "nombre": "WordPress",
        "icono": "M12 2a10 10 0 100 20 10 10 0 000-20z M8 9l4 8 4-8",
        "descripcion": "Publica o actualiza entradas vía la API REST de WordPress.",
        "ayuda_sidebar": "Requiere una credencial tipo Basic Auth con tu usuario y Application Password de WordPress (no la contraseña de login). La base_url debe terminar en /wp-json/wp/v2.",
        "campos": [
            {"name": "endpoint", "label": "Recurso", "widget": "select", "choices": ["posts", "pages", "media"], "initial": "posts"},
            {"name": "method", "label": "Operación", "widget": "select", "choices": ["POST", "PUT", "DELETE"], "initial": "POST"},
            {"name": "status_defecto", "label": "Estado al publicar", "widget": "select", "choices": ["draft", "publish"], "initial": "draft"}
        ]
    },
    "tavily-search": {
        "nombre": "Tavily Search",
        "icono": "M10 2a8 8 0 100 16 8 8 0 000-16z M16 16l4 4",
        "descripcion": "Búsqueda web optimizada para agentes de IA.",
        "ayuda_sidebar": "Obtén tu API Key gratis en tavily.com. La base_url de la credencial debe ser https://api.tavily.com. El método es POST.",
        "campos": [
            {"name": "method", "label": "Método", "widget": "select", "choices": ["POST"], "initial": "POST"},
            {"name": "search_depth", "label": "Profundidad", "widget": "select", "choices": ["basic", "advanced"], "initial": "advanced"},
            {"name": "max_results", "label": "Máx. resultados", "widget": "number", "initial": 5, "min": 1, "max": 10}
        ]
    },
    "custom": {
        "nombre": "Personalizada",
        "icono": "M12 3v18 M3 12h18",
        "descripcion": "Construye la configuración JSON a mano.",
        "ayuda_sidebar": "Úsala cuando ningún nodo predefinido cubra tu caso. El JSON que escribas aquí es exactamente lo que recibirá el motor de ejecución.",
        "campos": []
    }
}


def _inferir_tipo_herramienta(herramienta):
    """Intenta inferir el tipo de nodo a partir de la configuración JSON existente."""
    if not herramienta.configuracion:
        return "custom"
    config = herramienta.configuracion
    # Heurísticas basadas en claves características (orden de más específico a más general)
    if "search_depth" in config and "max_results" in config:
        return "tavily-search"
    if "spreadsheet_id" in config and "sheet_name" in config:
        return "google-sheets"
    if "status_defecto" in config and config.get("endpoint") in ["posts", "pages", "media"]:
        return "wordpress-connector"
    # Supabase: detectar por claves típicas o valores de endpoint
    if config.get("endpoint") and isinstance(config.get("endpoint"), str):
        endpoint = config.get("endpoint", "").lower()
        if "supabase" in endpoint or endpoint.startswith("/rest/v1/") or "tabla" in endpoint or endpoint in ["posts", "users", "comments"]:
            return "supabase-query"
    # HTTP Request genérico (body_template es distintivo)
    if "body_template" in config:
        return "http_request"
    if "method" in config and "endpoint" in config:
        return "http_request"
    return "custom"


def _serializar_campos_a_json(tool_type, post_data, configuracion_actual=None):
    """Convierte los campos del formulario estructurado a JSON para guardar en configuracion."""
    if tool_type == "custom":
        return configuracion_actual or {}
    
    tipo_def = TOOL_TYPES.get(tool_type, {})
    campos_def = tipo_def.get("campos", [])
    resultado = {}
    
    # Empezar con claves no mapeadas de la configuración actual (preservar claves exóticas)
    if configuracion_actual and isinstance(configuracion_actual, dict):
        claves_mapeadas = {c["name"] for c in campos_def}
        for k, v in configuracion_actual.items():
            if k not in claves_mapeadas:
                resultado[k] = v
    
    # Sobrescribir/añadir campos mapeados desde POST
    for campo in campos_def:
        name = campo["name"]
        value = post_data.get(name)
        if value is not None and value != "":
            # Conversión de tipos según widget
            if campo["widget"] == "number":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    value = campo.get("initial", 30)
            elif campo["widget"] == "textarea":
                # Intentar parsear JSON si parece JSON
                pass  # Se guarda como string
            resultado[name] = value
        elif name not in resultado and "initial" in campo:
            # Usar valor por defecto si no se envió nada y no hay valor previo
            resultado[name] = campo["initial"]
    
    return resultado


def _parsear_json_desde_campos(config_json, tool_type):
    """Extrae valores de campos estructurados desde un JSON para poblar el formulario."""
    if not config_json or not isinstance(config_json, dict):
        return {}
    resultado = {}
    tipo_def = TOOL_TYPES.get(tool_type, {})
    campos_def = tipo_def.get("campos", [])
    for campo in campos_def:
        name = campo["name"]
        if name in config_json:
            resultado[name] = config_json[name]
    return resultado


class WorkflowForm(forms.ModelForm):
    class Meta:
        model = Workflow
        fields = ["nombre", "descripcion"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
        }

@login_required
def lista_tareas(request):
    estado_filtro = request.GET.get('estado')
    tareas_qs = Tarea.objects.all().order_by('-id')
    if estado_filtro:
        tareas_qs = tareas_qs.filter(estado=estado_filtro)
    paginator = Paginator(tareas_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'panel/tareas.html', {'page_obj': page_obj, 'estado_filtro': estado_filtro})

@login_required
def crear_tarea(request):
    """Crea una tarea con agente manual o asignado automáticamente."""
    error = None
    agentes = Agente.objects.select_related("modelo").order_by("nombre")
    if request.method == "POST":
        texto = request.POST.get("texto", "").strip()
        keyword = request.POST.get("keyword", "").strip()
        instrucciones = request.POST.get("instrucciones", "").strip()
        agente_id = request.POST.get("agente_id", "").strip()
        if not texto:
            error = "El texto es obligatorio."
        else:
            if agente_id:
                agente = (
                    agentes.filter(pk=agente_id).first()
                    if agente_id.isdigit()
                    else None
                )
                if agente is None:
                    error = "El agente seleccionado no existe."
            else:
                agente = (
                    Agente.objects.filter(modelo__activo=True)
                    .select_related("modelo")
                    .order_by("pk")
                    .first()
                )
                if agente is None:
                    error = "No hay agentes activos disponibles"
            if error is None and agente.modelo is not None and not agente.modelo.activo:
                error = "El agente seleccionado no está activo."
            if error is None:
                proveedor = agente.modelo.proveedor if agente.modelo else None
                if proveedor and proveedor.limite_tokens_diario > 0:
                    if proveedor.tokens_consumidos_hoy >= proveedor.limite_tokens_diario:
                        error = "El proveedor ha alcanzado su límite diario de tokens."
                if error is None:
                    habilidad_id = request.POST.get('habilidad_id')
                    if habilidad_id:
                        try:
                            habilidad = Habilidad.objects.get(pk=habilidad_id)
                        except Habilidad.DoesNotExist:
                            messages.error(request, "La habilidad seleccionada no existe.")
                            return redirect('crear_tarea')
                    else:
                        # Fallback: usar la primera habilidad del agente
                        habilidad = agente.habilidades.first()
                        if not habilidad:
                            messages.error(request, "El agente no tiene habilidades asignadas.")
                            return redirect('crear_tarea')
                    payload = {"texto": texto}
                    if keyword:
                        payload["keyword"] = keyword
                    if instrucciones:
                        payload["instrucciones"] = instrucciones
                    tarea = Tarea.objects.create(
                        agente=agente,
                        habilidad=habilidad,
                        estado=Tarea.Estado.COLA,
                        payload=payload,
                    )
                    ejecutar_tarea(tarea.pk)
                    messages.success(
                        request,
                        f"Tarea creada y encolada con el agente {agente.nombre}.",
                    )
                    return redirect("lista_tareas")
    return render(
        request,
        "panel/crear_tarea.html",
        {"error": error, "agentes": agentes},
    )

@login_required
def detalle_tarea(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    ultimo_artefacto = tarea.artefactos.order_by('-id').first()
    ultima_ejecucion = tarea.ejecuciones.order_by('-id').first()
    destinos = DestinoPublicacion.objects.filter(activa=True).order_by('nombre')
    return render(request, 'panel/tareas.html', {
        'tarea': tarea,
        'ultimo_artefacto': ultimo_artefacto,
        'ultima_ejecucion': ultima_ejecucion,
        'destinos': destinos,
    })

@login_required
def aprobar_tarea(request):
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        tarea = get_object_or_404(Tarea, pk=task_id)
        if tarea.estado == 'revision':
            tarea.estado = 'ok'
            tarea.save()
            if tarea.paso_workflow is not None:
                continuar_workflow(
                    tarea.paso_workflow.workflow.pk,
                    tarea.paso_workflow.orden + 1,
                )
            ultimo_artefacto = tarea.artefactos.order_by('-id').first()
            if ultimo_artefacto:
                meta = ultimo_artefacto.metadata or {}
                meta['aprobado_por'] = request.user.username
                meta['aprobado_en'] = timezone.now().isoformat()
                ultimo_artefacto.metadata = meta
                ultimo_artefacto.save()
        if request.headers.get('HX-Request'):
            return render(request, 'panel/fila_tarea.html', {'tarea': tarea})
        return redirect('lista_tareas')
    return redirect('lista_tareas')

@login_required
@require_POST
def eliminar_tarea(request, pk):
    tarea = get_object_or_404(Tarea, pk=pk)
    tarea.delete()
    return redirect("lista_tareas")


@login_required
@require_POST
def acciones_lote_tareas(request):
    action = request.POST.get('action')
    task_ids = request.POST.getlist('task_ids')
    if not task_ids:
        messages.warning(request, "No se seleccionó ninguna tarea.")
        return redirect('lista_tareas')

    if action == 'eliminar':
        Tarea.objects.filter(pk__in=task_ids).delete()
        messages.success(request, f"{len(task_ids)} tarea(s) eliminada(s).")
    elif action == 'aprobar':
        count = 0
        for t_id in task_ids:
            try:
                tarea = Tarea.objects.get(pk=t_id, estado='revision')
                tarea.estado = 'ok'
                tarea.save()
                if tarea.paso_workflow:
                    from apps.engine.tasks import continuar_workflow
                    continuar_workflow.func(tarea.paso_workflow.workflow.pk, tarea.paso_workflow.orden + 1)
                count += 1
            except Tarea.DoesNotExist:
                continue
        messages.success(request, f"{count} tarea(s) aprobada(s).")
    else:
        messages.warning(request, "Acción no válida.")
    return redirect('lista_tareas')


@login_required
@require_POST
def acciones_lote_ejecuciones(request):
    """Borra por lote las ejecuciones seleccionadas (solo acción 'eliminar')."""
    action = request.POST.get('action')
    ejecucion_ids = request.POST.getlist('ejecucion_ids')
    if not ejecucion_ids:
        messages.warning(request, "No se seleccionó ninguna ejecución.")
        return redirect('lista_ejecuciones')

    if action == 'eliminar':
        count, _ = Ejecucion.objects.filter(pk__in=ejecucion_ids).delete()
        messages.success(request, f"{count} ejecución(es) eliminada(s).")
    else:
        messages.warning(request, "Acción no válida.")
    return redirect('lista_ejecuciones')


@login_required
@require_POST
def publicar_tarea(request, pk):
    """Envía el último artefacto de una tarea aprobada a WordPress como borrador.

    Obligatorio usar un DestinoPublicacion activo (credenciales de integración,
    no de proveedor LLM). Si no hay destino válido, se muestra error y se redirige.
    """
    tarea = get_object_or_404(Tarea, pk=pk)
    if tarea.estado != 'ok':
        messages.error(request, "Solo se puede publicar una tarea en estado 'ok'.")
        return redirect('detalle_tarea', pk=tarea.pk)

    ultimo_artefacto = tarea.artefactos.order_by('-id').first()
    if not ultimo_artefacto:
        messages.error(request, "La tarea no tiene un artefacto para publicar.")
        return redirect('detalle_tarea', pk=tarea.pk)

    destino_id = request.POST.get('destino_id')
    destino = None

    if destino_id:
        try:
            destino = DestinoPublicacion.objects.get(pk=destino_id, activa=True)
        except DestinoPublicacion.DoesNotExist:
            messages.error(request, "El destino de publicación seleccionado no existe o está inactivo.")
            return redirect('detalle_tarea', pk=tarea.pk)

    if not destino:
        messages.error(request, "Debe configurar y seleccionar un Destino de Publicación válido en Integraciones antes de publicar.")
        return redirect('detalle_tarea', pk=tarea.pk)

    try:
        # Credenciales del destino de publicación (cifradas en BD,
        # descifradas en memoria mediante EncryptedTextField).
        api_key = f"{destino.usuario}:{destino.credenciales}"
        base_url = destino.url
        wp = WordPressProvider(api_key=api_key, base_url=base_url)
        meta = ultimo_artefacto.metadata or {}
        # Orden de precedencia: metadata estructurada -> payload -> fallback.
        titulo = meta.get('titulo') or (tarea.payload or {}).get('titulo', f"Tarea #{tarea.pk}")
        contenido_md = meta.get('contenido') or ultimo_artefacto.contenido
        # Convertir Markdown a HTML antes de enviar a WordPress.
        contenido = markdown.markdown(contenido_md)
        slug = meta.get('slug') or None
        meta_description = meta.get('meta_description') or None
        focus_keyword = meta.get('focus_keyword') or None
        tipo_publicacion = request.POST.get('tipo_publicacion', 'post')
        link = wp.crear_borrador(
            titulo=titulo,
            contenido=contenido,
            metadata=meta,
            tipo=tipo_publicacion,
            slug=slug,
            meta_description=meta_description,
            focus_keyword=focus_keyword,
        )
        wp.close()
    except Exception:
        messages.error(request, "Error al enviar a WordPress.")
        return redirect('detalle_tarea', pk=tarea.pk)

    meta = tarea.payload or {}
    meta['wordpress_link'] = link
    meta['enviado_a_wordpress'] = True
    tarea.payload = meta
    tarea.save()
    messages.success(request, f"Enviado a WordPress como borrador: {link}")
    return redirect('detalle_tarea', pk=tarea.pk)


def login_panel(request):
    if request.user.is_authenticated:
        return redirect('lista_tareas')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('lista_tareas')
        else:
            error = 'Credenciales inválidas'
    return render(request, 'panel/base.html', {'error': error, 'is_login': True})

def logout_panel(request):
    auth_logout(request)
    return redirect('login_panel')


@login_required
def configuracion(request):
    proveedores = Proveedor.objects.all().order_by("nombre")
    form_proveedor = ProveedorForm()
    form_modelo = ModeloLLMForm()
    mostrar_form_proveedor = request.GET.get("nuevo_proveedor") == "1"
    mostrar_form_modelo = request.GET.get("nuevo_modelo") == "1"
    return render(request, "panel/configuracion.html", {
        "proveedores": proveedores,
        "form_proveedor": form_proveedor,
        "form_modelo": form_modelo,
        "mostrar_form_proveedor": mostrar_form_proveedor,
        "mostrar_form_modelo": mostrar_form_modelo,
    })


@login_required
def crear_proveedor(request):
    if request.method == "POST":
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("configuracion")
    else:
        form = ProveedorForm()
    return render(request, "panel/configuracion.html", {
        "form_proveedor": form,
        "mostrar_form_proveedor": True,
    })


@login_required
def crear_modelo(request):
    if request.method == "POST":
        form = ModeloLLMForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("configuracion")
    else:
        form = ModeloLLMForm()
    return render(request, "panel/configuracion.html", {
        "form_modelo": form,
        "mostrar_form_modelo": True,
    })


@login_required
def crear_habilidad(request):
    if request.method == "POST":
        form = HabilidadForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("configuracion")
    else:
        form = HabilidadForm()
    return render(request, "panel/configuracion.html", {
        "form_proveedor": ProveedorForm(),
        "form_modelo": ModeloLLMForm(),
        "form_habilidad": form,
        "mostrar_form_habilidad": True,
        "proveedores": Proveedor.objects.all().order_by("nombre"),
    })


@login_required
def crear_agente(request):
    habilidades = Habilidad.objects.all().order_by("nombre")
    modelos = (
        ModeloLLM.objects.filter(activo=True)
        .select_related("proveedor")
        .order_by("prioridad", "id")
    )
    if request.method == "POST":
        form = AgenteForm(request.POST)
        if form.is_valid():
            agente = form.save()
            agente.habilidades.set(request.POST.getlist("habilidades"))
            return redirect("configuracion")
    else:
        form = AgenteForm()
    return render(request, "panel/agente_form.html", {
        "form": form,
        "habilidades": habilidades,
        "modelos": modelos,
        "habilidades_seleccionadas": request.POST.getlist("habilidades"),
    })


@login_required
def lista_habilidades(request):
    habilidades = Habilidad.objects.all().order_by("nombre")
    return render(request, "panel/lista_habilidades.html", {
        "habilidades": habilidades,
    })


@login_required
def editar_habilidad(request, pk):
    habilidad = get_object_or_404(Habilidad, pk=pk)
    if habilidad.es_sistema:
        messages.warning(
            request,
            "Estás editando un recurso del sistema. Usa Restaurar para volver a los valores de fábrica.",
        )
    if request.method == "POST":
        form = HabilidadForm(request.POST, instance=habilidad)
        if form.is_valid():
            form.save()
            return redirect("lista_habilidades")
    else:
        form = HabilidadForm(instance=habilidad)
    return render(request, "panel/lista_habilidades.html", {
        "form": form,
        "habilidad": habilidad,
    })


@login_required
@require_POST
def eliminar_habilidad(request, pk):
    habilidad = get_object_or_404(Habilidad, pk=pk)
    if habilidad.es_sistema:
        messages.error(request, "No se pueden modificar recursos del sistema.")
        return redirect("lista_habilidades")
    try:
        habilidad.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: está siendo utilizado en tareas o workflows activos.",
        )
        return redirect("lista_habilidades")
    return redirect("lista_habilidades")


@login_required
def lista_formatos(request):
    """Listado de formatos de salida."""
    formatos = FormatoSalida.objects.order_by("nombre")
    return render(request, "panel/lista_formatos.html", {"formatos": formatos})


@login_required
def crear_formato(request):
    """Crea un formato de salida."""
    if request.method == "POST":
        form = FormatoSalidaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Formato de salida creado.")
            return redirect("lista_formatos")
    else:
        form = FormatoSalidaForm()
    return render(request, "panel/formato_form.html", {"form": form, "accion": "Crear"})


@login_required
def editar_formato(request, pk):
    """Edita un formato de salida existente."""
    formato = get_object_or_404(FormatoSalida, pk=pk)
    if formato.es_sistema:
        messages.warning(
            request,
            "Estás editando un recurso del sistema. Usa Restaurar para volver a los valores de fábrica.",
        )
    if request.method == "POST":
        form = FormatoSalidaForm(request.POST, instance=formato)
        if form.is_valid():
            form.save()
            messages.success(request, "Formato de salida actualizado.")
            return redirect("lista_formatos")
    else:
        form = FormatoSalidaForm(instance=formato)
    return render(request, "panel/formato_form.html", {"form": form, "accion": "Editar", "formato_editar": formato})


@login_required
@require_POST
def eliminar_formato(request, pk):
    """Elimina un formato de salida con protecciones."""
    formato = get_object_or_404(FormatoSalida, pk=pk)
    if formato.es_sistema:
        messages.error(request, "No se pueden modificar recursos del sistema.")
        return redirect("lista_formatos")
    try:
        formato.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: está siendo utilizado por agentes o tareas.",
        )
        return redirect("lista_formatos")
    messages.success(request, f"Formato '{formato.nombre}' eliminado.")
    return redirect("lista_formatos")


@login_required
def lista_herramientas(request):
    """Listado de herramientas externas."""
    herramientas = Herramienta.objects.order_by("nombre")
    return render(request, "panel/lista_herramientas.html", {"herramientas": herramientas})


@login_required
def crear_herramienta(request):
    """Crea una herramienta externa. Si no hay ?tipo=, muestra el catálogo."""
    tipo_param = request.GET.get("tipo")
    
    # Si no hay tipo, mostrar catálogo
    if not tipo_param or tipo_param not in TOOL_TYPES:
        return render(request, "panel/herramienta_catalogo.html", {
            "tool_types": TOOL_TYPES,
        })
    
    tool_type = tipo_param
    tipo_def = TOOL_TYPES[tool_type]
    
    if request.method == "POST":
        # Verificar si viene en modo avanzado (checkbox envía "on" en HTML, True en test client)
        advanced_mode_raw = request.POST.get("advanced_mode")
        advanced_mode = advanced_mode_raw in ("on", "True", "true", "1", True)
        
        form = HerramientaForm(request.POST)
        if form.is_valid():
            herramienta = form.save(commit=False)
            if advanced_mode:
                # Usar el JSON crudo del textarea configuracion
                try:
                    raw_json = request.POST.get("configuracion", "{}")
                    herramienta.configuracion = json.loads(raw_json)
                except json.JSONDecodeError:
                    messages.error(request, "El JSON en modo avanzado no es válido.")
                    return render(request, "panel/herramienta_form.html", {
                        "form": form,
                        "accion": "Crear",
                        "tool_type": tool_type,
                        "tipo_def": tipo_def,
                        "tool_types": TOOL_TYPES,
                        "valores_campos": _parsear_json_desde_campos(form.cleaned_data.get("configuracion") or {}, tool_type),
                        "error_json": True,
                    })
            else:
                # Serializar campos estructurados a JSON
                herramienta.configuracion = _serializar_campos_a_json(tool_type, request.POST)
            
            herramienta.save()
            messages.success(request, "Herramienta creada.")
            return redirect("lista_herramientas")
    else:
        form = HerramientaForm()
    
    # Valores iniciales para el formulario estructurado
    valores_campos = {}
    configuracion_inicial = form.initial.get("configuracion") if hasattr(form, 'initial') else None
    if configuracion_inicial:
        valores_campos = _parsear_json_desde_campos(configuracion_inicial, tool_type)
    
    return render(request, "panel/herramienta_form.html", {
        "form": form,
        "accion": "Crear",
        "tool_type": tool_type,
        "tipo_def": tipo_def,
        "tool_types": TOOL_TYPES,
        "valores_campos": valores_campos,
    })


@login_required
def editar_herramienta(request, pk):
    """Edita una herramienta existente con formulario dinámico según tipo."""
    herramienta = get_object_or_404(Herramienta, pk=pk)
    if herramienta.es_sistema:
        messages.warning(
            request,
            "Estás editando un recurso del sistema. Usa Restaurar para volver a los valores de fábrica.",
        )
    
    # Inferir tipo desde la configuración existente, pero permitir override desde POST
    tool_type = _inferir_tipo_herramienta(herramienta)
    if request.method == "POST":
        # Permitir que el formulario sobrescriba el tipo inferido
        posted_tool_type = request.POST.get("tool_type")
        if posted_tool_type and posted_tool_type in TOOL_TYPES:
            tool_type = posted_tool_type
    tipo_def = TOOL_TYPES.get(tool_type, TOOL_TYPES["custom"])
    
    if request.method == "POST":
        # Permitir que el formulario sobrescriba el tipo inferido
        posted_tool_type = request.POST.get("tool_type")
        if posted_tool_type and posted_tool_type in TOOL_TYPES:
            tool_type = posted_tool_type
        tipo_def = TOOL_TYPES.get(tool_type, TOOL_TYPES["custom"])
        
        # Verificar si viene en modo avanzado (checkbox envía "on" en HTML, True en test client)
        advanced_mode_raw = request.POST.get("advanced_mode")
        advanced_mode = advanced_mode_raw in ("on", "True", "true", "1", True)
        
        form = HerramientaForm(request.POST, instance=herramienta)
        if form.is_valid():
            if advanced_mode:
                # Usar el JSON crudo del textarea configuracion
                try:
                    raw_json = request.POST.get("configuracion", "{}")
                    herramienta.configuracion = json.loads(raw_json)
                    herramienta.save()
                    messages.success(request, "Herramienta actualizada.")
                    return redirect("lista_herramientas")
                except json.JSONDecodeError:
                    messages.error(request, "El JSON en modo avanzado no es válido.")
                    valores_campos = _parsear_json_desde_campos(herramienta.configuracion, tool_type)
                    return render(request, "panel/herramienta_form.html", {
                        "form": form,
                        "accion": "Editar",
                        "herramienta_editar": herramienta,
                        "tool_type": tool_type,
                        "tipo_def": tipo_def,
                        "tool_types": TOOL_TYPES,
                        "valores_campos": valores_campos,
                        "error_json": True,
                    })
            else:
                # Serializar campos estructurados a JSON, preservando claves no mapeadas
                herramienta.configuracion = _serializar_campos_a_json(tool_type, request.POST, herramienta.configuracion)
                herramienta.save()
                messages.success(request, "Herramienta actualizada.")
                return redirect("lista_herramientas")
    else:
        form = HerramientaForm(instance=herramienta)
    
    # Poblar valores_campos desde la configuración actual
    valores_campos = _parsear_json_desde_campos(herramienta.configuracion, tool_type)
    
    return render(request, "panel/herramienta_form.html", {
        "form": form,
        "accion": "Editar",
        "herramienta_editar": herramienta,
        "tool_type": tool_type,
        "tipo_def": tipo_def,
        "tool_types": TOOL_TYPES,
        "valores_campos": valores_campos,
    })


@login_required
@require_POST
def eliminar_herramienta(request, pk):
    """Elimina una herramienta con protecciones."""
    herramienta = get_object_or_404(Herramienta, pk=pk)
    if herramienta.es_sistema:
        messages.error(request, "No se pueden modificar recursos del sistema.")
        return redirect("lista_herramientas")
    try:
        herramienta.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: está siendo utilizada por agentes.",
        )
        return redirect("lista_herramientas")
    messages.success(request, f"Herramienta '{herramienta.nombre}' eliminada.")
    return redirect("lista_herramientas")


@login_required
@require_POST
def restaurar_habilidad(request, pk):
    """Restaura los valores de fábrica de una habilidad del sistema."""
    habilidad = get_object_or_404(Habilidad, pk=pk)
    if not habilidad.es_sistema:
        messages.error(request, "Este recurso no es del sistema.")
        return redirect("lista_habilidades")
    default = defaults.HABILIDADES_SISTEMA.get(habilidad.slug)
    if default is None:
        messages.error(request, "No hay valores por defecto para este recurso.")
        return redirect("editar_habilidad", pk=habilidad.pk)
    habilidad.nombre = default["nombre"]
    habilidad.instrucciones = default["instrucciones"]
    habilidad.modo_ejecucion = default["modo_ejecucion"]
    habilidad.save(update_fields=["nombre", "instrucciones", "modo_ejecucion"])
    messages.success(request, "Valores de fábrica restaurados correctamente.")
    return redirect("editar_habilidad", pk=habilidad.pk)


@login_required
@require_POST
def restaurar_formato(request, pk):
    """Restaura los valores de fábrica de un formato del sistema."""
    formato = get_object_or_404(FormatoSalida, pk=pk)
    if not formato.es_sistema:
        messages.error(request, "Este recurso no es del sistema.")
        return redirect("lista_formatos")
    default = defaults.FORMATOS_SISTEMA.get(formato.slug)
    if default is None:
        messages.error(request, "No hay valores por defecto para este recurso.")
        return redirect("editar_formato", pk=formato.pk)
    formato.nombre = default["nombre"]
    formato.descripcion = default["descripcion"]
    formato.esquema = default["esquema"]
    formato.version = default["version"]
    formato.permite_parcial = default["permite_parcial"]
    formato.plantilla_formato = default["plantilla_formato"]
    formato.save(update_fields=[
        "nombre", "descripcion", "esquema", "version",
        "permite_parcial", "plantilla_formato",
    ])
    messages.success(request, "Valores de fábrica restaurados correctamente.")
    return redirect("editar_formato", pk=formato.pk)


@login_required
@require_POST
def restaurar_herramienta(request, pk):
    """Restaura los valores de fábrica de una herramienta del sistema."""
    herramienta = get_object_or_404(Herramienta, pk=pk)
    if not herramienta.es_sistema:
        messages.error(request, "Este recurso no es del sistema.")
        return redirect("lista_herramientas")
    default = defaults.HERRAMIENTAS_SISTEMA.get(herramienta.slug)
    if default is None:
        messages.error(request, "No hay valores por defecto para este recurso.")
        return redirect("editar_herramienta", pk=herramienta.pk)
    herramienta.nombre = default["nombre"]
    herramienta.tipo = default["tipo"]
    herramienta.descripcion = default["descripcion"]
    herramienta.configuracion = default["configuracion"]
    herramienta.save(update_fields=["nombre", "tipo", "descripcion", "configuracion"])
    messages.success(request, "Valores de fábrica restaurados correctamente.")
    return redirect("editar_herramienta", pk=herramienta.pk)


@login_required
def lista_credenciales(request):
    """Lista de credenciales centralizadas con gestión de ARM API Key."""
    credenciales = Credencial.objects.all().order_by("nombre")

    if request.method == "POST":
        if request.POST.get("rotar_arm_api_key"):
            new_key = f"arm_{secrets.token_urlsafe(32)}"
            env_path = settings.BASE_DIR / '.env'
            set_key(env_path, 'ARM_API_KEY', new_key)
            settings.ARM_API_KEY = new_key
            messages.success(
                request,
                "ARM API Key renovada exitosamente. Actualiza tus servicios externos con la nueva clave."
            )
            return redirect("lista_credenciales")

    api_key = getattr(settings, "ARM_API_KEY", "") or ""
    if len(api_key) > 16:
        api_key_masked = api_key[:8] + "****" + api_key[-4:]
    else:
        api_key_masked = "****"

    return render(request, "panel/lista_credenciales.html", {
        "credenciales": credenciales,
        "api_key_masked": api_key_masked,
        "api_key_full": api_key,
        "url_webhook": request.build_absolute_uri("/api/webhook/"),
    })


@login_required
def crear_credencial(request):
    """Crea una credencial centralizada."""
    if request.method == "POST":
        form = CredencialForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Credencial creada correctamente.")
            return redirect("lista_credenciales")
    else:
        form = CredencialForm()
    return render(request, "panel/credencial_form.html", {"form": form, "accion": "Crear"})


@login_required
def editar_credencial(request, pk):
    """Edita una credencial existente."""
    credencial = get_object_or_404(Credencial, pk=pk)
    if credencial.es_sistema:
        messages.warning(
            request,
            "Estás editando un recurso del sistema. Usa Restaurar para volver a los valores de fábrica."
        )
    if request.method == "POST":
        form = CredencialForm(request.POST, instance=credencial)
        if form.is_valid():
            form.save()
            messages.success(request, "Credencial actualizada.")
            return redirect("lista_credenciales")
    else:
        form = CredencialForm(instance=credencial)
    return render(request, "panel/credencial_form.html", {"form": form, "accion": "Editar", "credencial_editar": credencial})


@login_required
@require_POST
def eliminar_credencial(request, pk):
    """Elimina una credencial con protecciones."""
    credencial = get_object_or_404(Credencial, pk=pk)
    if credencial.es_sistema:
        messages.error(request, "No se pueden modificar recursos del sistema.")
        return redirect("lista_credenciales")
    try:
        credencial.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: está siendo utilizada por herramientas."
        )
        return redirect("lista_credenciales")
    messages.success(request, f"Credencial '{credencial.nombre}' eliminada.")
    return redirect("lista_credenciales")


@login_required
@require_GET
def descubrir_tablas(request, pk):
    """
    Descubre las tablas de una base de datos Supabase usando la OpenAPI spec.

    Requiere una credencial de tipo 'api_key' o 'bearer' con base_url en metadata.
    Devuelve JSON con lista de tablas o error.
    """
    credencial = get_object_or_404(Credencial, pk=pk)

    # Validar tipo de credencial
    if credencial.tipo not in (Credencial.Tipo.API_KEY, Credencial.Tipo.BEARER):
        return JsonResponse(
            {"error": "Tipo de credencial no soportado para descubrimiento de tablas. Use 'api_key' o 'bearer'."},
            status=400,
        )

    # Obtener base_url del metadata
    metadata = credencial.metadata or {}
    base_url = metadata.get("base_url")
    if not base_url:
        return JsonResponse(
            {"error": "La credencial no tiene 'base_url' configurado en metadata."},
            status=400,
        )

    # Validar SSRF ANTES de hacer la petición
    try:
        validar_endpoint_seguro(base_url)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    # Construir headers de autenticación usando la fachada pública
    config = {
        "secreto_desencriptado": credencial.secreto_cifrado,
        "header_scheme": metadata.get("header_scheme", "bearer"),
        "header_name": metadata.get("header_name", "apikey"),
        "username": metadata.get("username", ""),
    }
    headers = construir_headers_autenticacion(config)

    # Asegurar que la URL termine en barra final para el spec OpenAPI de PostgREST
    url = base_url.rstrip("/") + "/"

    # Validar SSRF sobre la URL final
    try:
        validar_endpoint_seguro(url)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    # Petición a la OpenAPI spec de Supabase
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        # Log sanitizado sin exponer secretos
        logger.error(
            "Error de red al descubrir tablas de Supabase: %s",
            _sanitizar_config({"base_url": url, "headers": headers}),
        )
        return JsonResponse(
            {"error": "No se pudo conectar al endpoint de Supabase."},
            status=502,
        )

    if response.status_code != 200:
        return JsonResponse(
            {"error": f"Error HTTP {response.status_code} al obtener especificación OpenAPI."},
            status=502,
        )

    try:
        spec = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return JsonResponse(
            {"error": "La respuesta no es un JSON válido."},
            status=502,
        )

    # Extraer tablas de paths de OpenAPI
    paths = spec.get("paths", {})
    tablas = []
    for path_key in paths.keys():
        if not path_key.startswith("/"):
            continue
        if path_key == "/":
            continue
        if "{" in path_key:
            continue
        if path_key.startswith("/rpc/"):
            continue
        # Eliminar el slash inicial
        tabla = path_key[1:]
        if tabla:
            tablas.append(tabla)

    # Ordenar alfabéticamente
    tablas.sort()

    return JsonResponse({"tables": tablas})


@login_required
def lista_agentes(request):
    agentes = Agente.objects.select_related("modelo__proveedor").order_by("nombre")
    return render(request, "panel/lista_agentes.html", {
        "agentes": agentes,
    })


@login_required
def editar_agente(request, pk):
    agente = get_object_or_404(Agente, pk=pk)
    habilidades = Habilidad.objects.all().order_by("nombre")
    modelos = (
        ModeloLLM.objects.filter(activo=True)
        .select_related("proveedor")
        .order_by("prioridad", "id")
    )
    if request.method == "POST":
        form = AgenteForm(request.POST, instance=agente)
        habilidades_ids = request.POST.getlist("habilidades")

        # Persistir siempre la selección de habilidades para no perder el estado del usuario,
        # incluso si el formulario principal tiene errores de validación.
        agente.habilidades.set(habilidades_ids)

        if form.is_valid():
            form.save()
            messages.success(request, "Agente actualizado correctamente.")
            return redirect("lista_agentes")

        # Si el formulario es inválido, se re-renderiza con form.errors,
        # pero las habilidades ya se guardaron arriba.
        seleccionadas = habilidades_ids
    else:
        form = AgenteForm(instance=agente)
        seleccionadas = [str(pk) for pk in agente.habilidades.values_list("id", flat=True)]
    return render(request, "panel/lista_agentes.html", {
        "form": form,
        "agente": agente,
        "habilidades": habilidades,
        "modelos": modelos,
        "habilidades_seleccionadas": seleccionadas,
    })


@login_required
@require_POST
def eliminar_agente(request, pk):
    agente = get_object_or_404(Agente, pk=pk)
    try:
        agente.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: está siendo utilizado en tareas o workflows activos.",
        )
        return redirect("lista_agentes")
    return redirect("lista_agentes")


@login_required
def lista_workflows(request):
    workflows = (
        Workflow.objects.prefetch_related("pasos")
        .order_by("-fecha_creacion")
    )
    return render(request, "panel/lista_workflows.html", {"workflows": workflows})


@login_required
@require_POST
def ejecutar_workflow(request, pk):
    """Pone en ejecución un workflow en borrador y encola su primer paso."""
    workflow = get_object_or_404(Workflow, pk=pk)
    if workflow.estado != "borrador":
        messages.error(
            request, f"El workflow '{workflow.nombre}' no está en borrador."
        )
        return redirect("lista_workflows")
    workflow.estado = "en_ejecucion"
    workflow.save(update_fields=["estado"])
    continuar_workflow(workflow.pk, 1)
    messages.success(
        request, f"Workflow '{workflow.nombre}' puesto en ejecución."
    )
    return redirect("lista_workflows")


@login_required
def crear_workflow(request):
    PasoWorkflowFormSet = inlineformset_factory(
        Workflow,
        PasoWorkflow,
        fields=["orden", "habilidad", "agente", "modo_ejecucion"],
        extra=2,
        can_delete=True,
    )
    if request.method == "POST":
        form = WorkflowForm(request.POST)
        formset = PasoWorkflowFormSet(request.POST, prefix="pasos")
        if form.is_valid() and formset.is_valid():
            workflow = form.save()
            formset.instance = workflow
            formset.save()
            messages.success(request, f"Workflow '{workflow.nombre}' creado.")
            return redirect("lista_workflows")

    else:
        form = WorkflowForm()
        formset = PasoWorkflowFormSet(prefix="pasos")
    return render(
        request,
        "panel/formulario_workflow.html",
        {"form": form, "formset": formset},
    )


@login_required
def lista_equipos(request):
    equipos = (
        Equipo.objects.prefetch_related("agentes")
        .annotate(cantidad_agentes=models.Count("agentes"))
        .order_by("nombre")
    )
    return render(request, "panel/lista_equipos.html", {
        "equipos": equipos,
    })


@login_required
def crear_equipo(request):
    agentes = Agente.objects.select_related("modelo").order_by("nombre")
    error = None
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "").strip()
        agentes_ids = request.POST.getlist("agentes")
        if not nombre:
            error = "El nombre es obligatorio."
        elif Equipo.objects.filter(nombre=nombre).exists():
            error = "Ya existe un equipo con ese nombre."
        else:
            equipo = Equipo.objects.create(nombre=nombre, descripcion=descripcion)
            equipo.agentes.set(agentes_ids)
            messages.success(request, f"Equipo '{equipo.nombre}' creado.")
            return redirect("lista_equipos")
    return render(request, "panel/formulario_equipo.html", {
        "error": error,
        "agentes": agentes,
    })


@login_required
def editar_equipo(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    agentes = Agente.objects.select_related("modelo").order_by("nombre")
    seleccionados = [
        str(pk) for pk in equipo.agentes.values_list("id", flat=True)
    ]
    error = None
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "").strip()
        agentes_ids = request.POST.getlist("agentes")
        if not nombre:
            error = "El nombre es obligatorio."
        elif Equipo.objects.exclude(pk=pk).filter(nombre=nombre).exists():
            error = "Ya existe un equipo con ese nombre."
        else:
            equipo.nombre = nombre
            equipo.descripcion = descripcion
            equipo.save()
            equipo.agentes.set(agentes_ids)
            messages.success(request, f"Equipo '{equipo.nombre}' actualizado.")
            return redirect("lista_equipos")
    return render(request, "panel/formulario_equipo.html", {
        "error": error,
        "equipo": equipo,
        "agentes": agentes,
        "agentes_seleccionados": seleccionados,
    })


@login_required
@require_POST
def eliminar_equipo(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    nombre = equipo.nombre
    equipo.delete()
    messages.success(request, f"Equipo '{nombre}' eliminado.")
    return redirect("lista_equipos")


@login_required
def dashboard(request):
    """Vista de resumen con métricas generales del sistema."""
    tareas_cola = Tarea.objects.filter(estado='cola').count()
    tareas_ok = Tarea.objects.filter(estado='ok').count()
    tareas_fallo = Tarea.objects.filter(estado='fallo').count()
    tokens_hoy = Proveedor.objects.aggregate(total=Sum('tokens_consumidos_hoy'))['total'] or 0
    workflows_activos = Workflow.objects.filter(estado='en_ejecucion').count()
    return render(request, 'panel/dashboard.html', {
        'tareas_cola': tareas_cola,
        'tareas_ok': tareas_ok,
        'tareas_fallo': tareas_fallo,
        'tokens_hoy': tokens_hoy,
        'workflows_activos': workflows_activos,
    })


@login_required
def integraciones(request):
    """Gestiona las integraciones externas, rota la clave ARM API y
    permite crear destinos de publicación (desacoplados de proveedores LLM)."""
    integraciones_list = (
        IntegracionConfig.objects.all().order_by("nombre")
    )
    destinos = DestinoPublicacion.objects.all().order_by("nombre")
    nueva_clave_arm = None

    if request.method == "POST":
        form = DestinoPublicacionForm()
        if request.POST.get("rotar_arm_api"):
            nueva_clave_arm = IntegracionConfig.rotar_clave_arm()
        elif request.POST.get("crear_destino"):
            form = DestinoPublicacionForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(
                    request, "Destino de publicación creado correctamente."
                )
                return redirect("integraciones")
    else:
        form = DestinoPublicacionForm()

    return render(request, "panel/integraciones.html", {
        "integraciones": integraciones_list,
        "destinos": destinos,
        "form_destino": form,
        "nueva_clave_arm": nueva_clave_arm,
    })


@login_required
def editar_destino(request, pk):
    """Edita un destino de publicación, reutilizando DestinoPublicacionForm.

    Si `cambiar_credenciales` NO está marcado, se conserva la credencial
    cifrada original para no sobrescribirla con el valor enmascarado.
    """
    destino = get_object_or_404(DestinoPublicacion, pk=pk)
    credenciales_originales = destino.credenciales
    if request.method == "POST":
        form = DestinoPublicacionForm(request.POST, instance=destino)
        if form.is_valid():
            destino_obj = form.save(commit=False)
            if not form.cleaned_data.get('cambiar_credenciales'):
                destino_obj.credenciales = credenciales_originales
            else:
                nueva = (
                    request.POST.get('nueva_credenciales')
                    or form.cleaned_data.get('credenciales')
                    or credenciales_originales
                )
                destino_obj.credenciales = nueva
            destino_obj.save()
            messages.success(
                request, f"Destino '{destino_obj.nombre}' actualizado."
            )
            return redirect("integraciones")
    else:
        form = DestinoPublicacionForm(instance=destino)
    return render(request, "panel/integraciones.html", {
        "destinos": (
            DestinoPublicacion.objects.all().order_by("nombre")
        ),
        "form_destino": form,
        "destino_editar": destino,
    })


@login_required
@require_POST
def eliminar_destino(request, pk):
    """Elimina un destino con protección contra ProtectedError."""
    destino = get_object_or_404(DestinoPublicacion, pk=pk)
    nombre = destino.nombre
    try:
        destino.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar el destino: está siendo utilizado por "
            "tareas o workflows activos.",
        )
        return redirect("integraciones")
    messages.success(request, f"Destino '{nombre}' eliminado.")
    return redirect("integraciones")


@login_required
def lista_proveedores(request):
    """Lista de proveedores con sus modelos anidados."""
    proveedores = (
        Proveedor.objects.prefetch_related('modelos')
        .order_by('nombre')
    )
    return render(request, 'panel/lista_proveedores.html', {
        'proveedores': proveedores,
    })


@login_required
def editar_proveedor(request, pk):
    """Edita un proveedor existente, reutilizando ProveedorForm."""
    proveedor = get_object_or_404(Proveedor, pk=pk)
    clave_original = proveedor.api_key
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            proveedor_obj = form.save(commit=False)
            if not form.cleaned_data.get('cambiar_api_key'):
                proveedor_obj.api_key = clave_original
            else:
                nueva_key = form.cleaned_data.get('nueva_api_key') or request.POST.get('nueva_api_key')
                proveedor_obj.api_key = nueva_key if nueva_key else clave_original
            proveedor_obj.save()
            return redirect("lista_proveedores")
    else:
        form = ProveedorForm(instance=proveedor)
    return render(request, "panel/lista_proveedores.html", {
        "proveedores": (
            Proveedor.objects.prefetch_related('modelos')
            .order_by('nombre')
        ),
        "form": form,
        "proveedor_editar": proveedor,
    })


@login_required
def lista_modelos(request):
    """Listado plano de todos los modelos de IA con su proveedor."""
    modelos = (
        ModeloLLM.objects.select_related('proveedor')
        .order_by('proveedor__nombre', 'model_id')
    )
    return render(request, 'panel/lista_modelos.html', {'modelos': modelos})


@login_required
def lista_ejecuciones(request):
    """Historial de solo lectura de todas las ejecuciones de IA."""
    ejecuciones_qs = (
        Ejecucion.objects
        .select_related('tarea__agente__modelo__proveedor')
        .order_by('-id')
    )
    paginator = Paginator(ejecuciones_qs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'panel/lista_ejecuciones.html', {'page_obj': page_obj})


@login_required
def editar_modelo(request, pk):
    """Edita un modelo LLM existente, reutilizando ModeloLLMForm."""
    modelo = get_object_or_404(ModeloLLM, pk=pk)
    if request.method == "POST":
        form = ModeloLLMForm(request.POST, instance=modelo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Modelo '{modelo.model_id}' actualizado.")
            return redirect("lista_modelos")
    else:
        form = ModeloLLMForm(instance=modelo)
    return render(request, "panel/lista_modelos.html", {
        "modelos": (
            ModeloLLM.objects.select_related('proveedor')
            .order_by('proveedor__nombre', 'model_id')
        ),
        "form": form,
        "modelo_editar": modelo,
    })


@login_required
@require_POST
def eliminar_modelo(request, pk):
    """Elimina un modelo con protección contra ProtectedError."""
    modelo = get_object_or_404(ModeloLLM, pk=pk)
    modelo_id = modelo.model_id
    try:
        modelo.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: tiene agentes o tareas asociadas."
        )
        return redirect("lista_modelos")
    messages.success(request, f"Modelo '{modelo_id}' eliminado.")
    return redirect("lista_modelos")


@login_required
@require_POST
def eliminar_proveedor(request, pk):
    """Elimina un proveedor con protección contra ProtectedError."""
    proveedor = get_object_or_404(Proveedor, pk=pk)
    nombre = proveedor.nombre
    try:
        proveedor.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: tiene modelos asociados."
        )
        return redirect("lista_proveedores")
    messages.success(request, f"Proveedor '{nombre}' eliminado.")
    return redirect("lista_proveedores")


@login_required
@require_POST
def eliminar_workflow(request, pk):
    """Elimina un workflow con validación de estado y protección contra ProtectedError."""
    workflow = get_object_or_404(Workflow, pk=pk)
    if workflow.estado == "en_ejecucion":
        messages.error(request, "No se puede eliminar un workflow en ejecución.")
        return redirect("lista_workflows")
    nombre = workflow.nombre
    try:
        workflow.delete()
    except ProtectedError:
        messages.error(
            request,
            "No se puede eliminar: tiene pasos o tareas asociadas."
        )
        return redirect("lista_workflows")
    messages.success(request, f"Workflow '{nombre}' eliminado.")
    return redirect("lista_workflows")
