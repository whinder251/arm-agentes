# Estándar de diseño UI/UX — ARM Flow

## 1. Objetivo

Mantener una interfaz coherente, clara, profesional y usable en todos los módulos de ARM. Las nuevas pantallas deben parecer parte del mismo producto y reutilizar el sistema de diseño ya implementado.

Esta guía describe el sistema existente; no autoriza a rediseñarlo sin un paso aprobado.

## 2. Fuente de verdad

- Hoja central: `static/css/app.css`.
- Layout y navegación compartidos: `apps/panel/templates/panel/base.html`.
- Las vistas nuevas deben extender la plantilla base y reutilizar clases y tokens existentes.
- Antes de crear una clase, busca si ya existe una clase equivalente en `app.css`.
- No reintroduzcas bloques `<style>` en plantillas ni CSS duplicado por vista.
- No cambies la paleta, tipografía, radios o estructura global por preferencia personal del agente.

## 3. Tokens existentes

Los valores actuales de `static/css/app.css` son la referencia. Si se actualizan en el futuro, esta documentación debe actualizarse en el mismo cambio.

### Paleta

| Token | Valor actual | Uso |
|---|---|---|
| `--bg-primary` | `#F5F5F7` | Fondo principal |
| `--bg-secondary` | `#1F1F23` | Sidebar / superficie oscura |
| `--bg-surface` | `#FFFFFF` | Superficies y contenido |
| `--bg-surface-hover` | `#F2F2F7` | Hover y fondos suaves |
| `--text-primary` | `#1D1D1F` | Texto principal |
| `--text-secondary` | `#6E6E73` | Texto secundario |
| `--text-tertiary` | `#8E8E93` | Metadatos y navegación |
| `--text-inverse` | `#FFFFFF` | Texto sobre fondo oscuro |
| `--accent-primary` | `#6366F1` | Acento principal índigo |
| `--accent-primary-hover` | `#4F46E5` | Hover del acento |
| `--success` | `#34C759` | Estado exitoso |
| `--warning` | `#FF9500` | Advertencia |
| `--error` | `#FF3B30` | Error / acción destructiva |
| `--info` | `#0071E3` | Información |

No uses colores literales nuevos si existe un token semántico equivalente. No conviertas el azul informativo en color de marca: el acento principal actual es índigo.

### Tipografía

- Familia: `Inter, -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif`.
- Usa jerarquías claras y pesos 500, 600 y 700 según los tokens.
- Mantén legibilidad y contraste; no reduzcas textos importantes para hacer caber más contenido.
- Los metadatos deben ser secundarios, pero seguir siendo legibles.

### Espaciado, radios y sombras

- Espaciado: `--space-xs` 4px, `--space-sm` 8px, `--space-md` 16px, `--space-lg` 24px, `--space-xl` 32px.
- Radios: `--radius-sm` 6px, `--radius-md` 8px, `--radius-lg` 12px.
- Sombra base: `--shadow-sm`.
- Transición: `--transition-fast`.

### Layout existente

- Sidebar oscuro de 240px en escritorio.
- Área de contenido flexible con `min-width: 0`.
- Tarjetas blancas con borde sutil y radio grande.
- Tablas con líneas horizontales, sin saturación visual.
- La estructura exacta debe respetar `base.html` y los estilos existentes.

## 4. Componentes

Reutiliza primero las clases disponibles en `app.css`, entre ellas:

- Botones: `.btn-primary`, `.btn-secondary`, `.btn-danger`.
- Estados: `.badge`, `.badge-success`, `.badge-warning`, `.badge-error`, `.badge-info`.
- Superficies: `.tarjeta`.
- Tablas: `.tabla`.
- Layout y formularios: `.content`, `.sidebar`, `.form-group` y `.input` cuando estén definidos.
- Componentes específicos ya existentes deben conservar sus clases y comportamiento.

No inventes una segunda nomenclatura para resolver el mismo patrón. Si falta un componente transversal necesario, propón añadirlo a `app.css`, no copiarlo en cada template.

## 5. Estructura de página

- Cada vista debe tener un título claro y, cuando ayude, una descripción breve.
- Coloca la acción principal en una ubicación predecible y usa el mismo patrón de encabezado entre vistas.
- Agrupa información relacionada; evita tarjetas por cada dato si una tabla o lista es más clara.
- Prioriza la tarea principal del usuario y reduce elementos decorativos.
- No agregues gráficos, métricas o paneles que no respondan a una necesidad real.
- Mantén densidad visual equilibrada: suficiente información sin saturar.
- Evita scroll horizontal accidental. Para tablas amplias, define un contenedor responsive y una estrategia de columnas.

## 6. Formularios

- Etiquetas visibles y asociadas a sus controles.
- Indica campos obligatorios y formatos esperados.
- Conserva los nombres de campos, `id`, `name`, CSRF y estructuras de formsets existentes salvo que el cambio lo requiera.
- Muestra errores cerca del campo y conserva los valores válidos cuando sea posible.
- Usa estados focus visibles; no elimines el outline sin reemplazo accesible.
- Los controles deshabilitados deben distinguirse visualmente y no ser la única explicación de una restricción.
- Evita formularios excesivamente largos; agrupa por secciones con títulos descriptivos.
- Las acciones destructivas deben estar separadas de las acciones principales y requerir confirmación.

## 7. Estados de interfaz obligatorios

Toda vista que dependa de datos o acciones debe considerar, según corresponda:

- Cargando / procesando.
- Datos disponibles.
- Estado vacío con explicación y siguiente acción útil.
- Error recuperable con mensaje comprensible.
- Sin permiso / sesión expirada.
- Éxito y confirmación de la acción.
- Acción deshabilitada con explicación cuando el usuario no pueda ejecutarla.

No muestres éxito antes de confirmar la respuesta del servidor. Evita errores técnicos crudos en la interfaz.

## 8. Responsive

- Comprueba escritorio, tablet y móvil.
- El contenido debe poder reducirse sin solapamientos.
- El sidebar debe tener un comportamiento usable en pantallas estrechas; no asumas que el ancho de escritorio existe en móvil.
- Los formularios deben pasar a una columna cuando el ancho no permita dos.
- Las tablas deben ofrecer una solución consciente (scroll dentro del contenedor, columnas prioritarias o presentación alternativa).
- Botones y controles deben tener áreas de interacción adecuadas.
- No ocultes acciones importantes únicamente en hover.

## 9. Accesibilidad

- Usa HTML semántico: botones para acciones, enlaces para navegación, labels para campos.
- Mantén navegación por teclado y foco visible.
- No uses solo color para comunicar estados.
- Añade texto accesible a iconos funcionales; los iconos decorativos deben ocultarse a lectores de pantalla.
- Usa contraste suficiente y jerarquía de encabezados lógica.
- No uses emojis como iconos de interfaz. Prioriza los SVG existentes o iconos del sistema aprobado.
- Respeta `prefers-reduced-motion` cuando introduzcas animaciones.

## 10. JavaScript y comportamiento

- Mantén JavaScript pequeño y limitado a interacción de interfaz.
- No dupliques en JavaScript reglas de autorización o validación crítica del servidor.
- Evita listeners duplicados y mutaciones globales innecesarias.
- Maneja estados de carga, errores y doble envío.
- No insertes datos no confiables mediante `innerHTML`; usa APIs seguras o codificación contextual.
- No introduzcas frameworks ni dependencias de frontend sin aprobación.

## 11. Prohibiciones visuales

- No usar fondos crema o sepia.
- No usar gradientes genéricos morado/azul asociados a plantillas de IA.
- No usar emojis como iconos.
- No añadir sombras duras, bordes gruesos o colores saturados sin justificación.
- No crear tarjetas simétricas por decoración.
- No aplicar estilos inline ni bloques CSS embebidos como sustituto del sistema central.
- No alterar la identidad ARM Flow para una pantalla aislada.

## 12. Verificación visual

Los tests Django no demuestran por sí solos que el layout sea correcto. Para cambios de UI:

- Ejecuta los tests y `manage.py check`.
- Inspecciona el template y las clases utilizadas.
- Comprueba que no se introdujo CSS embebido o duplicado.
- Si existe navegador/herramienta visual disponible, revisa la vista en escritorio y móvil.
- Si no se pudo realizar una inspección visual, decláralo como pendiente; no afirmes que el diseño quedó visualmente validado.
