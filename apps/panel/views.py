from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from apps.core.models import Tarea

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
