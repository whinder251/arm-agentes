# Estándar de pruebas y verificación — ARM

## 1. Objetivo

Cada cambio debe aportar evidencia proporcional al riesgo. Una comprobación sintáctica no sustituye una prueba de comportamiento, y una prueba unitaria no demuestra por sí sola que el flujo completo funcione.

## 2. Principios

- Prueba el comportamiento observable y las reglas de negocio, no detalles internos innecesarios.
- Incluye casos correctos, inválidos, límites y fallos.
- Los tests deben ser deterministas y repetibles.
- No llames APIs, servicios de IA, WordPress ni otros servicios reales desde la suite.
- Usa `respx` y fixtures para simular HTTP cuando corresponda.
- No debilites una aserción ni elimines una prueba para hacer pasar un cambio.
- No marques como probado algo que no se ejecutó en esta sesión.

## 3. Tipos de pruebas

### Unitarias

Para funciones de dominio, validadores, normalización, cálculos, selección de modelos y reglas aisladas. Deben ser rápidas y no depender de red.

### Integración

Para interacciones entre modelos, servicios, transacciones, adaptadores, API y workers. Usa la base de pruebas y mocks controlados.

### API

Comprueba autenticación, permisos, validación, códigos HTTP, estructura de respuesta, límites y rechazo de entradas malformadas.

### Panel y formularios

Comprueba autenticación, autorización, validación, mensajes, estados y que el usuario no pueda acceder a recursos ajenos.

### Workers y workflows

Comprueba encadenamiento, orden, idempotencia, reintentos, estados finales, cuotas, errores y recuperación ante fallos.

### UI

Los tests de plantilla pueden validar elementos y contratos HTML, pero no garantizan layout, responsive ni accesibilidad. Complementa con inspección visual cuando exista una herramienta disponible.

## 4. Casos que deben cubrirse

Según el área modificada, considera:

- Entrada válida e inválida.
- Campo ausente, nulo, vacío, demasiado largo o con tipo incorrecto.
- Usuario anónimo, usuario autenticado sin permiso y usuario autorizado.
- Recurso inexistente y recurso perteneciente a otro usuario/proyecto.
- Servicio externo lento, no disponible, respuesta inválida, 4xx y 5xx.
- Timeout, reintento, duplicación y ejecución concurrente.
- Cuota agotada y límite de frecuencia alcanzado.
- Fallo antes, durante y después de persistir.
- Estado vacío, carga, error y éxito en la interfaz.
- Migración sobre base con datos y ejecución repetida de comandos idempotentes.

No es necesario probar todos estos escenarios en cada cambio; selecciona los pertinentes y explica exclusiones relevantes.

## 5. Seguridad en pruebas

- Nunca uses secretos reales.
- Usa credenciales ficticias claramente identificables.
- Comprueba que las respuestas y logs no exponen tokens, contraseñas ni claves.
- Prueba rechazo de autenticación y autorización, no solo el camino exitoso.
- Prueba que el filtrado por usuario/proyecto se aplica a consultas y mutaciones.
- Prueba SSRF y validación de URL cuando se cambie el código de integraciones.
- Prueba límites de tamaño y validación de archivos cuando se cambie su procesamiento.
- Prueba que el contenido externo o prompt injection no pueda cambiar permisos ni activar herramientas no autorizadas.

## 6. Datos, transacciones y concurrencia

- Comprueba invariantes de base de datos y restricciones únicas.
- Prueba que operaciones compuestas hacen rollback ante fallo.
- Prueba contadores y cuotas bajo concurrencia cuando el código los modifica.
- Verifica que no se crean duplicados en reintentos.
- Comprueba que las tareas y workflows terminan en estados coherentes.
- No asumas que SQLite reproduce todos los comportamientos de PostgreSQL. Las pruebas específicas de producción deberán ejecutarse contra PostgreSQL al abrir el Bloque D.

## 7. Migraciones

Cuando un cambio modifica modelos:

1. Genera la migración.
2. Revisa el archivo generado manualmente.
3. Comprueba dependencias y operaciones destructivas.
4. Aplica la migración en la base de desarrollo.
5. Ejecuta las pruebas relevantes.
6. Considera datos existentes y estrategia de reversión.
7. No edites migraciones que ya se aplicaron; crea una nueva.

Para migraciones de credenciales, tokens o relaciones de proyecto, incluye una estrategia explícita de conservación, importación o invalidación segura.

## 8. Comandos de verificación actuales

En el entorno de desarrollo actual, usa PowerShell y ejecuta por separado:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe manage.py check
```

Para cambios de modelos, añade:

```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Al preparar producción, incorpora las comprobaciones del paso de despliegue, incluida la verificación de configuración de Django para producción y pruebas contra PostgreSQL. No ejecutes comandos de producción sin autorización.

## 9. Verificación de rendimiento

No conviertas cada cambio en un benchmark. Cuando una tarea afecte consultas o procesamiento:

- Define el escenario y el volumen de datos.
- Identifica la métrica que se quiere mejorar.
- Comprueba consultas repetidas o N+1.
- Compara tiempo, consultas o memoria antes y después.
- Documenta el método y resultado.
- Evita afirmar una mejora si no existe medición.

## 10. Criterio de cierre

El reporte final debe incluir:

- Archivos modificados.
- Comportamiento implementado.
- Pruebas ejecutadas y resultado exacto.
- Migraciones creadas/aplicadas, si corresponde.
- Verificaciones no ejecutadas y motivo.
- Riesgos o deuda técnica pendiente.

Un test en verde no equivale a una auditoría de seguridad completa ni a validación visual. Describe con precisión el alcance de la evidencia.
