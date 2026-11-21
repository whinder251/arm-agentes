---
name: design-linear-nod
description: Sistema de diseño Linear-Nod de ARM Agentes (tokens CSS, tipografía, tarjetas, botones, formularios, accesibilidad y anti-patrones). Úsala al crear o modificar templates, CSS, componentes de interfaz o cualquier pantalla del panel.
---

# Skill: Design System — Linear-Nod Hybrid

## Filosofía
Combinar la claridad funcional de Linear con la transparencia conversacional de Nod. El usuario siempre debe saber: qué está pasando, qué puede hacer, qué hizo el agente.

## Tipografía
- **Fuente principal**: System fonts (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`)
- **Jerarquía**:
  - H1: 24px, font-weight 600, color `--text-primary`
  - H2: 20px, font-weight 600
  - H3: 16px, font-weight 600 (títulos de tarjetas)
  - Body: 14px, font-weight 400, line-height 1.5
  - Small: 12px, color `--text-secondary` (metadatos, ayuda)
- **Espaciado**: Múltiplos de 4px (4, 8, 12, 16, 24, 32)

## Colores (variables CSS)

```css
:root {
  /* Fondo */
  --bg-primary: #fafafa;
  --bg-secondary: #f5f5f5;
  --bg-tertiary: #ebebeb;

  /* Texto */
  --text-primary: #171717;
  --text-secondary: #666666;   /* 4.8:1 sobre cualquier fondo de arriba */
  --text-tertiary: #a3a3a3;    /* SOLO decorativo o deshabilitado, nunca información */

  /* Bordes */
  --border-primary: #e5e5e5;
  --border-secondary: #d4d4d4;

  /* Acento de marca (decorativo: iconos grandes, indicadores, fondos suaves) */
  --accent-primary: #009CFF;

  /* Acento accesible (botones con texto blanco, enlaces, foco) */
  --accent-solid: #0070C0;     /* 5.1:1 con texto blanco; 4.9:1 como texto sobre --bg-primary */
  --accent-hover: #005FA3;

  /* Estados: fondos/iconos */
  --accent-success: #10b981;
  --accent-warning: #f59e0b;
  --accent-danger: #ef4444;

  /* Estados: cuando se usan COMO TEXTO (cumplen 4.5:1) */
  --accent-success-text: #047857;
  --accent-warning-text: #b45309;
  --accent-danger-text: #b91c1c;

  /* Sombras (sutil, no neomorfismo) */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
}
```

Regla de uso: los colores `--accent-primary`, `--accent-success`, `--accent-warning` y `--accent-danger` **no cumplen contraste como texto** sobre fondos claros. Para texto o botones con texto usar `--accent-solid` y las variantes `-text`.

## Componentes

### Tarjetas (.card)

```css
.card {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: 8px;
  padding: 16px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease;
}

.card:hover {
  box-shadow: var(--shadow-md);
}
```

### Botones

- **Primario** (`.btn-primary`): Fondo `--accent-solid`, texto blanco, `border-radius: 6px`, `padding: 8px 16px`. Hover: fondo `--accent-hover`.
- **Secundario** (`.btn-secondary`): Fondo transparente, borde `1px solid var(--border-primary)`, texto `--text-primary`.
- **Peligro** (`.btn-danger-sm`): Fondo transparente, texto `--accent-danger-text`, tamaño pequeño.
- **Hover**: Cambio de fondo o borde, nunca sombra dramática.
- **Active**: Escala `0.98` o cambio de fondo más oscuro.

### Foco visible

```css
:focus-visible {
  outline: 2px solid var(--accent-solid);
  outline-offset: 2px;
}
```

### Formularios (UX Crítica)

```css
.input, .textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  font-size: 14px;
  background: var(--bg-primary);
  transition: border-color 0.2s ease;
}

.input:focus, .textarea:focus {
  outline: none;
  border-color: var(--accent-solid);
  box-shadow: 0 0 0 3px rgba(0, 112, 192, 0.2);
}
```

## Reglas de UX para Formularios

### 1. Labels siempre visibles
- NUNCA usar placeholders como única etiqueta.
- Labels arriba del input, `font-size: 14px`, `font-weight: 500`, color `--text-primary`.

### 2. Help text contextual
- Texto de ayuda debajo del input, `font-size: 12px`, color `--text-secondary`.
- Explicar el "por qué", no el "qué".

### 3. Validación en tiempo real (cuando sea posible)
- Validar email, URLs, campos requeridos al perder el foco (blur).
- Mostrar errores con `--accent-danger-text` y un ícono SVG, junto al campo afectado.

### 4. Estados de carga
- Botones en estado de carga: deshabilitados + spinner SVG + texto "Procesando...".
- NUNCA permitir doble clic en botones de acción.

### 5. Confirmación de acciones destructivas
- Eliminar, archivar, descartar: siempre con `confirm()` nativo o modal.
- Mensaje claro: "¿Estás seguro de archivar esta tarea? Esta acción no se puede deshacer."

### 6. Feedback inmediato
- Acciones exitosas: `messages.success()` con texto específico.
- Acciones fallidas: `messages.error()` con texto genérico al usuario, detalle en logs.

### 7. Jerarquía de acciones
- Una sola acción primaria por vista.
- Acciones secundarias con estilo `.btn-secondary`.
- Acciones destructivas con estilo `.btn-danger-sm` y confirmación.

### 8. Formularios largos: agrupar y progresar
- Si el formulario tiene más de 6 campos, agrupar en secciones con `<fieldset>` o `<div class="seccion">`.
- Cada sección con título `<h3>` descriptivo.

### 9. Accesibilidad (a11y)
- Todos los inputs con `<label>` asociado (`for`/`id`).
- Contraste mínimo 4.5:1 para texto normal.
- Foco visible en todos los elementos interactivos.

### 10. Responsive básico
- Formularios en móvil: inputs al 100% del ancho.
- Botones de acción: apilados verticalmente en pantallas < 640px.

## Anti-patrones Prohibidos

- Placeholders como única etiqueta.
- Validación solo al enviar.
- Botones sin estado de carga.
- Mensajes de error genéricos.
- Estilos inline.
- Emojis como iconos de UI.
- Neomorfismo en botones de acción o indicadores de estado.
- Usar `--accent-primary`, `--accent-success`, `--accent-warning` o `--accent-danger` como color de texto.
- Usar `--text-tertiary` para información que el usuario necesita leer.
