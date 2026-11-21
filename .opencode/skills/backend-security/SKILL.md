---
name: backend-security
description: Reglas de seguridad backend y base de datos en ARM Agentes (ORM sin SQL crudo, autenticación, CSRF, secretos, protección SSRF en requests a URLs del usuario, validación de entradas). Úsala al escribir vistas, formularios, llamadas HTTP a URLs externas, acceso a BD o manejo de credenciales.
---

# Skill: Backend & Database Security

## Contexto
Aplicación Django que maneja datos de monitoreo web, credenciales de APIs y contenido extraído de terceros.

## Reglas Estrictas
- **ORM de Django**: NUNCA escribir SQL crudo (`raw()` o `cursor()`). Usar siempre el ORM para prevenir Inyección SQL.
- **Autenticación**: Todas las vistas deben estar protegidas con `@login_required`.
- **CSRF**: Todos los formularios POST deben incluir `{% csrf_token %}`. Las vistas que modifican datos usan `@require_POST`.
- **Secretos**: NUNCA registrar (log) API keys, tokens, contraseñas o datos personales de usuarios. Usar `django.conf.settings` para credenciales.
- **Validación de Entradas**: Usar `forms.py` para validar y limpiar todos los datos de entrada. No confiar en `request.POST` directo en las vistas.

## SSRF (Server-Side Request Forgery)
Al hacer `requests.get()` a URLs proporcionadas por el usuario, validar siempre el destino contra una lista de bloqueo de redes privadas:

- Rangos a bloquear: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16` (incluye el metadata de la nube `169.254.169.254`), `0.0.0.0`, y en IPv6 `::1`, `fc00::/7`, `fe80::/10`.
- Validar la **IP resuelta**, no solo el texto del dominio: resolver el host (`socket.getaddrinfo`) y comprobar cada IP (módulo `ipaddress`: `is_private`, `is_loopback`, `is_link_local`, `is_reserved`).
- Permitir solo esquemas `http` y `https`.
- Una redirección puede apuntar a una red interna: desactivar `allow_redirects` o revalidar el destino en cada salto.
- Poner `timeout` explícito en toda petición.

Centralizar esta validación en una única función (ej. en `apps/engine`) y llamarla siempre antes de pedir una URL del usuario.

## Manejo de Errores
- Capturar excepciones específicas (ej. `requests.RequestException`, `ValidationError`).
- Nunca exponer tracebacks completos al usuario en producción. Usar `messages.error()` para feedback genérico.
