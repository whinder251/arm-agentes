# ARM - Agent Resource Management

Orquestador de agentes de IA para generación y publicación de contenido con validación determinista.

## Características

- Panel web estilo Apple/SaaS con dashboard de métricas en tiempo real.
- Workflows multi-paso con equipos de agentes y orquestación automática.
- API REST para integraciones externas (Pydantic v2, autenticación por header).
- Publicación directa en WordPress (como borrador).
- Cifrado de API keys con cryptography.fernet.
- Validación de cuotas de tokens en tiempo real.
- Verificadores deterministas de SEO, estilo y hechos.
- Vista de integraciones con API key visible.

## Requisitos

- Python 3.12+
- Windows 11 (o Linux/Mac)
- 8 GB de RAM mínimo

## Instalación

```powershell
git clone <repo>
cd "C:\Users\Drogo\Downloads\ARM agentes"
python -m venv .venv
```

Activar el entorno virtual:

```powershell
# Windows
.venv\Scripts\activate

# Linux / Mac
source .venv/bin/activate
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Aplicar migraciones y crear superusuario:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

## Variables de entorno obligatorias

Crea un archivo `.env` en la raíz del proyecto con el siguiente contenido:

```
# Clave de cifrado para api_key de proveedores (generar con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ARM_ENCRYPTION_KEY=tu-clave-fernet-aqui

# Clave de autenticación para la API REST (cadena segura de al menos 32 caracteres)
ARM_API_KEY=tu-api-key-segura-aqui

# Opcional: DEBUG de Django (True para desarrollo, False para producción)
DEBUG=True
```

## Ejecución

Servidor de desarrollo:

```powershell
python manage.py runserver
```

Worker de Huey (cola de tareas):

```powershell
python manage.py run_huey
```

## Arquitectura

- **core**: Modelos de dominio (Tarea, Proveedor, Habilidad, Agente, Workflow, PasoWorkflow, Equipo).
- **panel**: Vistas y plantillas del panel web (estilo Apple/SaaS).
- **engine**: Tareas asíncronas con Huey, ejecución de pipelines y orquestación de workflows.
- **providers**: Proveedores de IA (OpenRouter, Gemini, WordPress), router de proveedores y gestión de cuotas.
- **api**: API REST para sistemas externos (autenticación por token, Pydantic v2).
- **checks**: Verificadores deterministas de SEO, estilo y hechos.

## Licencia

MIT