from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.core.models import Tarea, Proveedor, ModeloLLM, Habilidad, Agente
from apps.engine.tasks import ejecutar_tarea
from apps.panel.forms import (
    AgenteForm,
    HabilidadForm,
    ModeloLLMForm,
    ProveedorForm,
)

@login_required
def lista_tareas(request):
    estado_filtro = request.GET.get('estado')
    tareas = Tarea.objects.all().order_by('-id')
    if estado_filtro:
        tareas = tareas.filter(estado=estado_filtro)
    return render(request, 'panel/tareas.html', {'tareas': tareas, 'estado_filtro': estado_filtro})

@login_required
def crear_tarea(request):
    """Crea una tarea asignada manualmente al agente seleccionado."""
    error = None
    agentes = Agente.objects.select_related("modelo").order_by("nombre")
    if request.method == "POST":
        texto = request.POST.get("texto", "").strip()
        keyword = request.POST.get("keyword", "").strip()
        instrucciones = request.POST.get("instrucciones", "").strip()
        agente_id = request.POST.get("agente_id", "").strip()
        if not texto:
            error = "El texto es obligatorio."
        elif not agente_id:
            error = "Debes seleccionar un agente"
        else:
            agente = agentes.filter(pk=agente_id).first() if agente_id.isdigit() else None
            if agente is None:
                error = "El agente seleccionado no existe."
            elif agente.modelo is not None and not agente.modelo.activo:
                error = "El agente seleccionado no está activo."
            else:
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
