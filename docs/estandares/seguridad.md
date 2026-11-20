# Estándar de seguridad — ARM

## 1. Objetivo y criterio

La seguridad es una condición de aceptación, no una mejora opcional. ARM administra usuarios, credenciales, proveedores de IA, integraciones externas y tareas que pueden producir efectos fuera del sistema.

Aplica defensa en profundidad. No confíes en el prompt, en el frontend, en el nombre de un agente ni en una respuesta de IA como mecanismo de autorización.

## 2. Identidad, autenticación y autorización

- Toda vista privada debe exigir autenticación.
- Toda acción debe comprobar autorización en el servidor, además de autenticación.
- No uses ocultar botones o enlaces como sustituto de permisos.
- Verifica permisos sobre el objeto concreto solicitado; evita IDOR/BOLA.
- Las acciones de crear, editar, eliminar, ejecutar, aprobar, publicar, administrar credenciales y consultar ejecuciones deben tener controles explícitos.
- Usa métodos HTTP apropiados y protección CSRF para acciones de sesión.
- Los endpoints API deben validar autenticación, formato, tamaño y permisos en cada petición.
- No confíes en identificadores enviados por el cliente para determinar propiedad o alcance.
- Al incorporar proyectos/espacios de trabajo, cada consulta y mutación deberá limitarse al proyecto autorizado. No basta con filtrar solo en la interfaz.
- No implementes permisos multiusuario o multitenencia parcial: diseña y prueba el aislamiento de extremo a extremo.

## 3. Secretos y credenciales

- Nunca guardes secretos en el repositorio, código, fixtures, capturas, documentación, respuestas HTTP ni logs.
- `.env` y archivos equivalentes no se leen ni modifican salvo autorización expresa para una tarea concreta.
- La clave maestra Fernet debe permanecer fuera de la base de datos y fuera del repositorio, suministrada por el entorno seguro del servidor.
- Cifra con el mecanismo existente las credenciales que ARM necesite recuperar para conectarse a servicios externos.
- Para tokens de autenticación que solo deban verificarse, almacena un hash seguro y compara en tiempo constante. No cifres de forma reversible algo que nunca necesitas recuperar.
- No registres el valor de una credencial, ni siquiera parcialmente, salvo una política explícita y segura de identificación.
- En el panel, muestra secretos enmascarados. Si un secreto solo se puede mostrar al crearlo, adviértelo y no lo vuelvas a revelar.
- La rotación debe invalidar o retirar la credencial anterior de forma controlada y documentada.
- No confundas credenciales de proveedores LLM con credenciales de integraciones como WordPress.
- Nunca generes o reemplaces claves automáticamente durante una migración sin aprobación y plan de compatibilidad.

## 4. API y abuso

- Usa HTTPS en producción.
- Valida el esquema, tipo, longitud y tamaño de toda entrada.
- Aplica límites de frecuencia y cuotas en el servidor; no dependas del cliente.
- Evita enumeración de recursos y respuestas que revelen si un secreto o usuario existe.
- Rechaza tokens ausentes, inválidos, revocados o desactivados.
- Define expiración o rotación de tokens cuando el caso de uso lo requiera.
- No devuelvas trazas, variables de entorno, rutas internas, consultas SQL ni detalles de proveedores.
- Limita el tamaño de cuerpos y respuestas.
- Registra eventos de autenticación y abuso sin incluir tokens ni datos sensibles.
- Los webhooks deben validar autenticidad (firma, secreto o mecanismo documentado), timestamp/replay cuando aplique e idempotencia.

## 5. Integraciones HTTP y SSRF

- Trata cualquier URL configurable o derivada de entrada externa como no confiable.
- Solo permite esquemas necesarios (normalmente HTTPS en producción); rechaza `file:`, `ftp:`, `gopher:` y esquemas no requeridos.
- Bloquea loopback, redes privadas, link-local, multicast, direcciones reservadas y endpoints de metadatos de nube, salvo excepción interna explícita.
- Resuelve y valida DNS; considera redirecciones y cambios de resolución para evitar bypass de SSRF.
- No sigas redirecciones automáticamente hacia destinos no validados.
- Define timeout de conexión y lectura, tamaño máximo de respuesta y límites de reintentos.
- No permitas que un usuario use una integración para escanear puertos o acceder a servicios internos.
- Mantén una lista de destinos permitidos cuando el tipo de integración lo permita.
- No uses `verify=False` ni desactives validación TLS para resolver errores de certificados.

## 6. Ejecución de agentes y herramientas

- El modelo no concede permisos. El servidor decide qué herramienta está habilitada para cada tarea, agente, usuario y proyecto.
- Aplica mínimo privilegio: habilita solo herramientas y operaciones necesarias.
- Separa lectura, escritura, publicación, eliminación y administración como permisos distintos cuando corresponda.
- Acciones con efectos externos relevantes (publicar, borrar, enviar mensajes, modificar registros) deben tener autorización explícita y, cuando corresponda, aprobación humana.
- Define límites duros de tokens, coste, duración, tamaño de contexto, llamadas, reintentos y concurrencia.
- No permitas que un agente cambie sus propios permisos, presupuesto, proveedor privilegiado o reglas de seguridad.
- Trata prompts, documentos, páginas web, correos, archivos y resultados de herramientas como datos no confiables. Una instrucción encontrada dentro de ellos no puede reemplazar las instrucciones del sistema ni conceder privilegios.
- No concatenes contenido no confiable en instrucciones privilegiadas sin delimitación y validación.
- Valida las salidas del modelo con esquemas y reglas de negocio antes de ejecutar herramientas o persistir cambios.
- No ejecutes código arbitrario generado por el modelo en el proceso Django ni en el worker.
- Evita shell, eval, exec, carga dinámica o ejecución de archivos enviados por usuarios. Si un caso futuro requiere sandbox, deberá diseñarse y aprobarse por separado.

## 7. Archivos y contenido

- Valida extensión, MIME real, tamaño y estructura del archivo; no confíes solo en el nombre o `Content-Type`.
- Define límites de tamaño y tiempo de procesamiento.
- Guarda archivos fuera de rutas ejecutables y evita servirlos como contenido activo.
- Genera nombres internos seguros; no uses rutas proporcionadas por el usuario directamente.
- Protege contra path traversal, archivos comprimidos maliciosos y descompresión excesiva.
- No proceses macros, scripts o contenido activo salvo necesidad y sandbox aprobados.
- Escapa contenido al renderizar HTML y evita marcar datos no confiables como `safe`.
- No insertes datos de usuarios en JavaScript o HTML sin codificación contextual.

## 8. Django y configuración de producción

- Mantén `DEBUG=False` en producción.
- Configura `ALLOWED_HOSTS` de forma explícita.
- Usa cookies de sesión y CSRF seguras bajo HTTPS (`Secure`, `HttpOnly` y `SameSite` apropiado).
- Revisa `CSRF_TRUSTED_ORIGINS`, CORS si se introduce, cabeceras de seguridad y política de contenido.
- No desactives CSRF globalmente para facilitar una integración.
- Mantén `SECRET_KEY` y claves de cifrado como secretos de infraestructura.
- Usa las protecciones ORM de Django; no construyas SQL concatenando entradas.
- Escapa la salida HTML y evita XSS almacenado/reflejado.
- Revisa permisos de archivos, copias de seguridad y acceso a la base de datos.
- Ejecuta `manage.py check --deploy` al preparar producción y resuelve o documenta cada advertencia relevante.

## 9. Huey, concurrencia y efectos externos

- No confíes en que una tarea de la cola se ejecutará exactamente una vez.
- Diseña tareas idempotentes y protege efectos externos frente a duplicados.
- Valida que el usuario y el proyecto siguen autorizados cuando el worker ejecuta la tarea, no solo al encolarla.
- Limita concurrencia por proveedor, integración, usuario o proyecto según corresponda.
- No mantengas transacciones abiertas durante llamadas de red.
- Los reintentos deben ser acotados y no repetir ciegamente acciones irreversibles.
- No expongas datos de otras tareas en logs o resultados.
- Los errores técnicos deben conservar contexto suficiente para depuración sin incluir secretos.

## 10. Auditoría y observabilidad

Registra, según la sensibilidad y necesidad:

- Usuario o actor del sistema.
- Acción y recurso afectado.
- Proyecto/espacio de trabajo, cuando exista.
- Fecha y resultado.
- Identificador de ejecución o correlación.

No registres contraseñas, tokens, claves API, cabeceras de autorización, cookies, claves de cifrado ni contenido privado completo por defecto. Usa redacción de secretos antes de enviar excepciones a logs.

## 11. Dependencias y respuesta ante incidentes

- Añade dependencias solo con aprobación.
- Revisa mantenimiento, procedencia, licencias y vulnerabilidades conocidas.
- No desactives verificaciones de seguridad para hacer pasar tests.
- Ante exposición de credenciales, detén su uso, informa al usuario y recomienda rotación. No copies el secreto en el reporte.
- Ante una vulnerabilidad, explica impacto, superficie afectada, mitigación y pruebas necesarias.
- No afirmes que ARM es “seguro” o “a prueba de ataques” por tener tests; describe qué controles se verificaron y cuáles faltan.

## 12. Revisión de seguridad mínima por cambio

Antes de cerrar, pregunta:

1. ¿La ruta requiere autenticación?
2. ¿El actor tiene permiso para esta acción y este objeto?
3. ¿Se valida toda entrada no confiable?
4. ¿Puede filtrarse un secreto o dato privado?
5. ¿Puede una URL externa acceder a redes internas?
6. ¿Puede el agente ejecutar una acción no autorizada?
7. ¿Hay límites de coste, tiempo, tamaño y frecuencia?
8. ¿Los reintentos pueden duplicar efectos?
9. ¿Los errores y logs revelan información sensible?
10. ¿Hay pruebas para los casos de rechazo y abuso?
