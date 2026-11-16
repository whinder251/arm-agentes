from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from django.views.decorators.http import require_POST
from django import forms
from django.conf import settings
from django.db import models
from django.db.models import Sum, ProtectedError
from django.core.paginator import Paginator
from django.forms import inlineformset_factory
import markdown
from apps.core.models import (
    Tarea, Proveedor, ModeloLLM, Habilidad, Agente, Equipo, Workflow, PasoWorkflow,
    Ejecucion, IntegracionConfig, DestinoPublicacion,
)
from apps.engine.tasks import ejecutar_tarea, continuar_workflow
from apps.providers.wordpress import WordPressProvider
from apps.panel.forms import (
    AgenteForm,
    DestinoPublicacionForm,
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
