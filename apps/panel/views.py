from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from apps.core.models import Tarea, Proveedor, ModeloLLM
from apps.panel.forms import ProveedorForm, ModeloLLMForm

@login_required
def lista_tareas(request):
    estado_filtro = request.GET.get('estado')
    tareas = Tarea.objects.all().order_by('-id')
    if estado_filtro:
        tareas = tareas.filter(estado=estado_filtro)
    return render(request, 'panel/tareas.html', {'tareas': tareas, 'estado_filtro': estado_filtro})

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
            return render(request, 'panel/tareas.html', {'tarea': tarea, 'single_row': True})
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
