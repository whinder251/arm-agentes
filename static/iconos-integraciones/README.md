# Iconos de integraciones para ARM

113 integraciones en 11 categorías y 14 iconos de navegación (estilo Centro de Mando).
Abre `vista-previa.html` en el navegador para verlos todos y buscar por nombre.

## Contenido

| Carpeta | Qué hay | Uso |
|---|---|---|
| `marca/` | 94 logotipos a color (SVG 24x24) | Listas y tarjetas de integraciones, con `<img>` |
| `mono/` | Los mismos 94 en un solo color (`currentColor`) | Insertados en línea, para que tomen el color del texto |
| `generico/` | 19 iconos neutros (trazo `currentColor`) | Servicios sin logotipo disponible: Slack, Microsoft, LinkedIn, OpenAI, Twilio, Salesforce y otros. No son el logotipo de la marca |
| `navegacion/` | 14 iconos de trazo (24x24, `currentColor`) | Menú y secciones: conversación, tareas, programaciones, uso y costes, confianza, bóveda, memoria, conexiones, agentes, workflows, herramientas, registro, monitoreo, biblioteca |
| `catalogo.json` | Nombre, categoría, tipo (`llm` o `integracion`), color, archivo y origen de cada icono | Fuente de datos para el panel |

La clave `tipo` mantiene la separación de ARM entre proveedores de IA (`llm`) e integraciones funcionales (`integracion`).

## Uso en Django

1. Copia la carpeta a `static/img/integraciones/`.
2. En la plantilla, con logotipo a color:

```django
{% load static %}
<img class="icono-integracion" src="{% static 'img/integraciones/marca/wordpress.svg' %}" alt="" width="24" height="24">
```

   Usa `alt=""` cuando el nombre ya aparece como texto al lado; si el icono va solo, pon el nombre en `alt`.
3. Con icono de un solo color que herede el color del texto, incluye el SVG en línea (`{% include %}` con el contenido de `mono/` o `navegacion/`).
4. El tamaño y el espaciado salen de una clase de `static/css/app.css`. No uses estilos inline. Si no existe una clase equivalente, propón añadir `.icono-integracion` a `app.css` en el paso correspondiente.

## Licencias y marcas

- Logotipos: [simple-icons](https://simpleicons.org) 16.38.0, licencia CC0-1.0.
- Iconos genéricos y de navegación: [Lucide](https://lucide.dev), licencia ISC.
- CC0 cubre los archivos, no las marcas. Los nombres y logotipos pertenecen a sus titulares. Úsalos solo para identificar la integración y revisa la guía de marca de cada servicio antes de publicarlos.
- Algunos titulares pidieron retirar sus logotipos de simple-icons (por ejemplo Slack, Microsoft, LinkedIn y OpenAI). Para esos servicios hay un icono genérico. Si necesitas el logotipo oficial, descárgalo del kit de prensa de la marca.

## Añadir más iconos

En una carpeta aparte, fuera del proyecto (ARM no usa Node), ejecuta `npm i simple-icons` y copia el SVG que necesites desde `node_modules/simple-icons/icons/`. Después añade su entrada a `catalogo.json`.
