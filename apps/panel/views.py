from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from django.views.decorators.http import require_POST
from django import forms
from django.db import models
from django.db.models import Sum
from django.forms import inlineformset_factory
from apps.core.models import (
    Tarea, Proveedor, ModeloLLM, Habilidad, Agente, Equipo, Workflow, PasoWorkflow,
)
from apps.engine.tasks import ejecutar_tarea, continuar_workflow
from apps.providers.wordpress import WordPressProvider
from apps.panel.forms import (
    AgenteForm,
    HabilidadForm,
    ModeloLLMForm,
    ProveedorForm,
)


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
    tareas = Tarea.objects.all().order_by('-id')
    if estado_filtro:
        tareas = tareas.filter(estado=estado_filtro)
    return render(request, 'panel/tareas.html', {'tareas': tareas, 'estado_filtro': estado_filtro})

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
                    habilidad = Habilidad.objects.filter(slug="reescritura").first()
                    if habilidad is None:
                        error = (
                            "No existe la habilidad 'reescritura'. Créala antes de "
                            "encolar una tarea."
                        )
                    else:
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
    return render(request, 'panel/tareas.html', {
        'tarea': tarea,
        'ultimo_artefacto': ultimo_artefacto,
        'ultima_ejecucion': ultima_ejecucion,
    })

@login_required
def aprobar_tarea(request):
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        tarea = get_object_or_404(Tarea, pk=task_id)
        if tarea.estado == 'revision':
            tarea.estado = 'ok'
            tarea.save()
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
def publicar_tarea(request, pk):
    """Envía el último artefacto de una tarea aprobada a WordPress como borrador."""
    tarea = get_object_or_404(Tarea, pk=pk)
    if tarea.estado != 'ok':
        messages.error(request, "Solo se puede publicar una tarea en estado 'ok'.")
        return redirect('detalle_tarea', pk=tarea.pk)

    ultimo_artefacto = tarea.artefactos.order_by('-id').first()
    if not ultimo_artefacto:
        messages.error(request, "La tarea no tiene un artefacto para publicar.")
        return redirect('detalle_tarea', pk=tarea.pk)

    proveedor = None
    if tarea.agente and tarea.agente.modelo:
        proveedor = tarea.agente.modelo.proveedor
    if not proveedor:
        messages.error(request, "La tarea no tiene un proveedor configurado.")
        return redirect('detalle_tarea', pk=tarea.pk)

    try:
        wp = WordPressProvider(api_key=proveedor.api_key, base_url=proveedor.base_url)
        titulo = (tarea.payload or {}).get('titulo', f"Tarea #{tarea.pk}")
        link = wp.crear_borrador(titulo=titulo, contenido=ultimo_artefacto.contenido)
        wp.close()
    except Exception as exc:
        messages.error(request, f"Error al enviar a WordPress: {exc}")
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
    habilidad.delete()
    return redirect("lista_habilidades")


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
        if form.is_valid():
            agente = form.save()
            agente.habilidades.set(request.POST.getlist("habilidades"))
            return redirect("lista_agentes")
        seleccionadas = request.POST.getlist("habilidades")
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
    agente.delete()
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
    continuar_workflow.delay(workflow.pk, 1)
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
