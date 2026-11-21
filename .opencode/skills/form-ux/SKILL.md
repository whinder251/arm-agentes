---
name: form-ux
description: Buenas prácticas de UX para formularios de ARM Agentes (orden de campos, valores por defecto, campos condicionales, errores específicos, estados de éxito, teclado y accesibilidad). Úsala al crear o modificar formularios, forms.py o templates con formularios.
---

# Skill: Form UX Best Practices

## Principio Fundamental
Un formulario debe sentirse como una conversación guiada, no como un interrogatorio.

## Reglas de Oro

### 1. Orden lógico de campos
- De lo general a lo específico
- De lo obligatorio a lo opcional
- Agrupar campos relacionados visualmente

### 2. Valores por defecto inteligentes
- Preseleccionar la opción más común
- Usar valores iniciales basados en el contexto
- NUNCA dejar campos vacíos si hay un valor obvio

### 3. Campos condicionales
- Mostrar/ocultar campos según selecciones previas
- Usar JavaScript simple (toggle de display), no recargas de página
- Animar la transición con CSS (opacity/height, no display:none abrupto)

### 4. Atajos de teclado
- Enter para enviar (si no hay textarea)
- Escape para cancelar
- Tab para navegar entre campos

### 5. Mensajes de error específicos
- Mal: "Este campo es requerido"
- Bien: "El nombre de la fuente es obligatorio para crear el monitoreo"
- Posicionar el error debajo del campo afectado, no al final del formulario

### 6. Progreso visible
- Para formularios de múltiples pasos, mostrar indicador de progreso (Paso 2 de 4)
- Permitir volver atrás sin perder datos

### 7. Confirmación de éxito clara
- Después de enviar: mensaje específico + redirección lógica
- Ejemplo: "Fuente 'Competencia SEO' creada. Ahora puedes ejecutarla o editarla."
- Botones de acción post-éxito: "Ver detalle", "Crear otra", "Volver al Centro de Mando"

## Ejemplo de Formulario Bien Diseñado

```html
<form method="post" action="{% url 'crear_investigacion' %}">
  {% csrf_token %}

  <div class="seccion">
    <h3 class="subtitulo">Información básica</h3>

    <div class="form-group">
      <label class="label" for="id_nombre">Nombre de la fuente</label>
      <input type="text" id="id_nombre" name="nombre" class="input" required />
      <p class="help-text">Usa un nombre descriptivo para identificar esta fuente en el Centro de Mando</p>
    </div>

    <div class="form-group">
      <label class="label" for="id_modo_busqueda">Modo de búsqueda</label>
      <select id="id_modo_busqueda" name="modo_busqueda" class="input">
        <option value="sitio">Rastreo de Sitio Web</option>
        <option value="busqueda" selected>Descubrir contenido</option>
        <option value="noticias">Seguir actualidad</option>
      </select>
      <p class="help-text">Elige cómo el sistema debe buscar contenido para esta fuente</p>
    </div>
  </div>

  <div class="acciones-formulario">
    <button type="submit" class="btn-primary">Crear fuente de monitoreo</button>
    <a href="{% url 'lista_investigaciones' %}" class="btn-secondary">Cancelar</a>
  </div>
</form>
```

Notas sobre el ejemplo:
- Muestra el **resultado esperado**. En la implementación, los campos se definen en `forms.py` con sus clases CSS en `widgets` (ver skill `django-architecture`), no escritos a mano en el template.
- La interfaz habla de "fuente" y "monitoreo", mientras que el modelo y las URLs se llaman `investigacion`. Mantener el vocabulario de la interfaz consistente en todos los textos visibles.

## Checklist de Revisión de Formularios
- [ ] Todos los campos tienen label visible
- [ ] Help text explica el "por qué", no el "qué"
- [ ] Valores por defecto inteligentes aplicados
- [ ] Campos condicionales funcionan sin recargar
- [ ] Validación en blur para campos críticos
- [ ] Botón de envío con estado de carga
- [ ] Mensaje de éxito específico después de enviar
- [ ] Navegación por teclado funcional
- [ ] Contraste de texto cumple WCAG AA
- [ ] Responsive en móvil (inputs 100% ancho)
