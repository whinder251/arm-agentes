# Reglas de estilo para el contenido generado

Este archivo lo consume apps/checks en el paso 5. Aplica al texto que producen los
agentes (artículos, titulares, metas), no al código Python.

El linter devuelve JSON con esta forma:
{"regla": "EST-001", "severidad": "alta", "posicion": 120, "mensaje": "...", "sugerencia": "..."}

Severidad alta bloquea la publicación automática y fuerza revisión humana.

## EST-001 - Palabras vetadas (alta)
Coincidencia por palabra completa, sin distinguir mayúsculas:
crucial, pivotal, vibrante, intrincado, panorama, entramado, testimonio,
multifacético, robusto, sólido, matices, seamless, delve, foster, tapestry,
landscape, innovador

## EST-002 - Frases vetadas (alta)
Patrones sobre el texto normalizado:
- sirve como|actúa como|funciona como
- no solo .{1,80} sino
- no es .{1,60}, es
- más que .{1,60}, es
- punto de inflexión|sentó las bases|papel vital|refleja tendencias
- a pesar de estos desafíos|perspectivas futuras
- destacando|asegurando|fomentando|abarcando
- ¡por supuesto!|espero que ayude|aquí tienes un desglose
- los expertos dicen|informes sugieren|observadores señalan
- amplia gama|anidado en el corazón de

## EST-003 - Comillas curvas (alta)
Presencia de U+201C, U+201D, U+2018 o U+2019. Se sustituyen por comillas rectas.

## EST-004 - Regla de tres (media)
Enumeraciones de exactamente tres elementos unidos por coma y "y".
Detección heurística: patrón de dos comas seguidas de "y" sin una cuarta coma.
Marca para revisión humana, no bloquea.

## EST-005 - Formato (media)
- Elementos de lista que empiezan por negrita seguida de dos puntos.
- Subtítulos en Title Case.
- Más de dos negritas por cada 300 palabras.
- Cierres que empiezan por "En conclusión" o "En resumen".

## EST-006 - Estructura del texto (baja)
- Párrafos de más de 70 palabras.
- Tres párrafos seguidos con longitud parecida, diferencia menor al 15%.
- Frases de más de 40 palabras.
- Párrafo final de una sola frase genérica.

## SEO-001 a SEO-006 - Comprobaciones técnicas (alta)
- Título: máximo 60 caracteres.
- Meta descripción: entre 140 y 155 caracteres.
- Un solo H1 en el documento.
- Slug en minúsculas, sin stopwords, máximo 60 caracteres.
- Densidad de la keyword principal entre 0,5% y 2%.
- Legibilidad INFLESZ igual o mayor a 55 para noticias generales.

## FCT-001 - Anclaje de hechos (alta)
Cifras y nombres propios presentes en la reescritura y ausentes en el original.
Cualquier entidad nueva bloquea la publicación y exige revisión humana.
Los falsos positivos por mayúscula de inicio de frase se filtran con una lista de
exclusión configurable.

## Configuración
Umbrales y listas se cargan desde este archivo. Cambiar una regla no requiere
tocar el código de apps/checks.