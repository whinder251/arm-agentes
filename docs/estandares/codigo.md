# Estándar de código, arquitectura y optimización — ARM

## 1. Objetivo

Mantener un código seguro, predecible, eficiente y fácil de modificar. Estas reglas se aplican al núcleo de ARM y a los módulos presentes o futuros. No obligan a introducir capas o patrones que el tamaño real del problema no justifique.

## 2. Antes de modificar

- Lee el código que participa directamente en el flujo y sus pruebas.
- Identifica quién llama al componente, qué datos recibe, qué persiste y qué contratos expone.
- Busca una implementación existente antes de crear otra.
- Identifica compatibilidad con SQLite actual, Huey, API, plantillas y tareas en cola.
- Enumera archivos y riesgos en el plan previo. No hagas exploraciones o refactors indiscriminados.

## 3. Responsabilidades

- **Modelos:** representar datos, relaciones, restricciones e invariantes del dominio. Evita colocar integraciones HTTP o procesos largos en métodos de modelo.
- **Servicios / dominio:** concentrar operaciones de negocio reutilizables y transacciones que no pertenecen a una vista.
- **Vistas:** autenticar, autorizar, validar la petición, invocar servicios y construir la respuesta. Evita lógica de negocio extensa.
- **Formularios / esquemas:** validar datos de entrada y presentar errores comprensibles.
- **Workers Huey:** ejecutar trabajo asíncrono, con estados persistidos, límites, reintentos controlados e idempotencia cuando sea necesaria.
- **Adaptadores de proveedor e integración:** encapsular protocolos externos y normalizar sus respuestas.
- **Plantillas y JavaScript:** presentar e interactuar; no duplicar reglas críticas de negocio que deben validarse en servidor.

No crees una capa de servicios, repositorios, factories o abstracciones genéricas solo por estilo. Introduce una abstracción cuando elimine duplicación real, aísle una dependencia externa o haga comprobable una regla importante.

## 4. Python y Django

- Usa nombres de clases y funciones en inglés, siguiendo la convención existente. La documentación, comentarios útiles y textos de interfaz se escriben en español.
- Prefiere funciones pequeñas con una responsabilidad clara y nombres que expresen intención.
- Evita funciones extensas, anidamiento excesivo, estado global mutable y dependencias circulares.
- Usa `settings` para configuración de infraestructura, no para secretos de negocio que deban administrarse por proyecto.
- Usa `transaction.atomic()` cuando varias escrituras deban confirmarse o revertirse como una unidad.
- Usa `F()` expressions, restricciones de base de datos o bloqueos apropiados para evitar condiciones de carrera; no confíes únicamente en una comprobación previa en Python.
- Define `on_delete`, `related_name`, índices y restricciones conscientemente.
- No guardes listas o diccionarios complejos en texto si existe un campo estructurado apropiado.
- Usa `update_fields` cuando corresponda y evita guardar campos innecesarios.
- No captures `Exception` para continuar como si nada. Si es imprescindible capturarla en un límite de ejecución, registra el fallo de forma segura, actualiza el estado coherentemente y conserva el contexto técnico sin secretos.
- No uses `save()` o señales como mecanismo oculto para coordinar workflows completos.

## 5. Persistencia, consultas y rendimiento

- Evita N+1: utiliza `select_related()` para relaciones singulares y `prefetch_related()` para relaciones múltiples cuando el patrón de acceso lo justifique.
- Selecciona solo campos necesarios en consultas grandes cuando sea útil (`only`, `defer`, `values`), sin crear complejidad innecesaria.
- Pagina listados que puedan crecer; no cargues colecciones ilimitadas en memoria.
- Evita consultas repetidas dentro de bucles. Agrupa o precarga datos.
- Añade índices únicamente para filtros, joins u ordenamientos frecuentes respaldados por el uso esperado.
- No agregues caché por defecto. Primero identifica el coste y define invalidación, expiración y consistencia.
- No paralelices por defecto. Evalúa límites del proveedor, concurrencia, cuotas, orden de workflows y capacidad de la máquina.
- Para operaciones costosas, define límites de tiempo, tamaño, memoria y cantidad de reintentos.
- No optimices prematuramente ni afirmes mejoras de rendimiento sin medición comparable.

## 6. API y validación de datos

- Valida toda entrada externa en el límite del sistema: formularios, API, webhooks, archivos y respuestas de proveedores.
- Usa Pydantic v2 para los contratos donde ya forma parte de la arquitectura; no dupliques validación incompatible entre capas.
- No confíes en que el frontend o el prompt de un agente haya validado los datos.
- Devuelve errores consistentes, sin stack traces, secretos ni detalles internos.
- Mantén compatibilidad de contratos; si un cambio es incompatible, documenta versión, migración y consumidores afectados.
- Usa códigos HTTP semánticos y no respondas éxito antes de que la operación haya sido aceptada o persistida según el contrato.

## 7. Huey y ejecución de tareas

- La cola no es la fuente de verdad: persiste estado, resultado, errores y datos necesarios para recuperar o auditar la ejecución.
- Diseña tareas para que un reintento no duplique publicaciones, cobros, mensajes ni otros efectos externos.
- Usa claves de idempotencia o comprobaciones persistidas cuando el efecto externo lo permita.
- Define timeout, reintentos y backoff explícitos; evita reintentos infinitos.
- Respeta orden y dependencias de workflows.
- Una tarea fallida debe dejar el workflow y los recursos relacionados en estados coherentes.
- Nunca mantengas una transacción de base de datos abierta durante una llamada de red prolongada.
- Reserva y consume cuotas de forma atómica y registra el consumo real cuando el proveedor lo informe.
- No registres prompts privados, credenciales ni contenido sensible de forma indiscriminada.

## 8. Integraciones externas

- Separa proveedores de modelos LLM de integraciones funcionales como WordPress, Slack o servicios externos.
- Encapsula HTTP en adaptadores reutilizables.
- Configura timeout de conexión y lectura, límites de respuesta y manejo explícito de códigos HTTP.
- Valida y normaliza respuestas externas antes de persistirlas.
- No hagas llamadas de red durante importaciones de módulos, señales inesperadas ni tests unitarios.
- Usa `httpx` y `respx` conforme al patrón existente.
- Mantén URL, credenciales, tipo de autenticación y capacidades específicas en la integración correspondiente, no mezcladas con la configuración del modelo LLM.

## 9. Código mantenible

- Evita duplicar lógica, constantes, consultas y fragmentos de plantilla.
- Extrae funciones compartidas cuando exista una responsabilidad común real.
- Evita clases base genéricas y configuraciones mágicas difíciles de seguir.
- Usa constantes con nombre para estados y valores repetidos cuando reduzcan errores.
- Documenta decisiones no obvias, invariantes y efectos secundarios; no comentes cada línea.
- Elimina imports y variables sin uso introducidos por el cambio.
- No dejes código muerto, `TODO` sin contexto ni ramas de depuración.
- No cambies nombres, rutas o formatos persistidos sin evaluar datos existentes y consumidores.

## 10. Optimización para el motor de IA

- Establece límites máximos de tokens de entrada y salida, duración, reintentos y coste cuando el proveedor lo permita.
- Evita repetir contexto completo en cada paso si solo se necesita una parte; no recortes contexto sin preservar requisitos y datos críticos.
- Registra modelo, proveedor, duración, tokens y resultado cuando estén disponibles.
- No selecciones un modelo solo por precio: considera compatibilidad, calidad requerida, latencia, límites y disponibilidad.
- Los fallbacks deben ser explícitos, observables y compatibles con el contrato de salida.
- Valida la salida estructurada antes de ejecutar acciones posteriores.
- Nunca permitas que texto generado por el modelo modifique permisos, límites de seguridad o configuración privilegiada.

## 11. Cuándo medir

Antes de introducir optimizaciones complejas, define la métrica afectada, por ejemplo:

- Número de consultas y tiempo de consulta.
- Tiempo de ejecución de una tarea.
- Memoria utilizada.
- Tokens de entrada y salida.
- Coste estimado y latencia por proveedor.
- Tasa de reintentos y fallos.

Compara antes y después con el mismo escenario. Si no hay evidencia de un problema, prefiere la solución más sencilla.
