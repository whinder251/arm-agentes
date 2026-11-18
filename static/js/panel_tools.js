/**
 * panel_tools.js — Utilidades para la UI de herramientas tipo n8n
 * Funciones para headers dinámicos, toggle modo avanzado, etc.
 */

(function() {
    'use strict';

    /**
     * Añade una fila de header (clave/valor) al contenedor
     * @param {HTMLElement} container - Contenedor #headers-container
     */
    function addHeaderRow(container) {
        const row = document.createElement('div');
        row.className = 'header-row';
        row.innerHTML = `
            <input type="text" name="header_key[]" class="input" placeholder="Nombre header" aria-label="Nombre header">
            <input type="text" name="header_value[]" class="input" placeholder="Valor" aria-label="Valor header">
            <button type="button" class="btn-danger-sm btn-header-remove" aria-label="Eliminar header">×</button>
        `;
        container.appendChild(row);
        
        // Delegar el evento de eliminar al botón nuevo
        row.querySelector('.btn-header-remove').addEventListener('click', function() {
            removeHeaderRow(this);
        });
    }

    /**
     * Elimina una fila de header
     * @param {HTMLButtonElement} btn - Botón .btn-header-remove clicado
     */
    function removeHeaderRow(btn) {
        const row = btn.closest('.header-row');
        if (row) {
            row.remove();
        }
    }

    /**
     * Alterna entre modo simple (campos estructurados) y avanzado (JSON crudo)
     * @param {HTMLInputElement} checkbox - Checkbox #id_advanced_mode
     * @param {HTMLElement} simpleContainer - Fieldset #fieldset-estructurado
     * @param {HTMLElement} jsonContainer - Div #fieldset-avanzado
     * @param {HTMLElement} errorDiv - Div #json-error
     */
    function toggleAdvancedMode(checkbox, simpleContainer, jsonContainer, errorDiv) {
        if (checkbox.checked) {
            // MODO AVANZADO: Serializar campos estructurados a JSON
            const config = {};
            
            // Recopilar campos del fieldset estructurado (excluyendo headers array)
            simpleContainer.querySelectorAll('[name]').forEach(function(el) {
                const name = el.name;
                if (name.endsWith('[]')) return; // Skip header arrays
                if (el.type === 'checkbox') {
                    config[name] = el.checked;
                } else if (el.type === 'number') {
                    config[name] = parseInt(el.value, 10) || 0;
                } else {
                    config[name] = el.value;
                }
            });
            
            // Recopilar headers
            const headers = {};
            simpleContainer.querySelectorAll('.header-row').forEach(function(row) {
                const keyInput = row.querySelector('input[name="header_key[]"]');
                const valInput = row.querySelector('input[name="header_value[]"]');
                if (keyInput && keyInput.value) {
                    headers[keyInput.value] = valInput ? valInput.value : '';
                }
            });
            if (Object.keys(headers).length > 0) {
                config.headers = headers;
            }
            
            // Escribir JSON en el textarea
            const textarea = jsonContainer.querySelector('textarea');
            if (textarea) {
                textarea.value = JSON.stringify(config, null, 2);
            }
            
            simpleContainer.classList.add('oculto');
            jsonContainer.classList.remove('oculto');
            if (errorDiv) errorDiv.classList.add('oculto');
            
        } else {
            // MODO SIMPLE: Parsear JSON y poblar campos
            const textarea = jsonContainer.querySelector('textarea');
            if (!textarea) return;
            
            try {
                const config = JSON.parse(textarea.value || '{}');
                
                // Poblar campos simples
                Object.keys(config).forEach(function(key) {
                    if (key === 'headers') return;
                    const el = simpleContainer.querySelector('[name="' + key + '"]');
                    if (el) {
                        if (el.type === 'checkbox') {
                            el.checked = !!config[key];
                        } else if (el.tagName === 'SELECT') {
                            el.value = config[key];
                        } else {
                            el.value = config[key];
                        }
                    }
                });
                
                // Poblar headers
                const container = document.getElementById('headers-container');
                if (container && config.headers && typeof config.headers === 'object') {
                    container.innerHTML = '';
                    Object.entries(config.headers).forEach(function([k, v]) {
                        const row = document.createElement('div');
                        row.className = 'header-row';
                        row.innerHTML = '<input type="text" name="header_key[]" class="input" value="' + escapeHtml(k) + '" placeholder="Nombre header"><input type="text" name="header_value[]" class="input" value="' + escapeHtml(String(v)) + '" placeholder="Valor"><button type="button" class="btn-danger-sm btn-header-remove" aria-label="Eliminar header">×</button>';
                        container.appendChild(row);
                    });
                }
                
                simpleContainer.classList.remove('oculto');
                jsonContainer.classList.add('oculto');
                if (errorDiv) errorDiv.classList.add('oculto');
                
            } catch (e) {
                if (errorDiv) {
                    errorDiv.textContent = 'JSON inválido: ' + e.message;
                    errorDiv.classList.remove('oculto');
                }
                // Mantener modo avanzado activo
                checkbox.checked = true;
            }
        }
    }

    /**
     * Escapa HTML para prevenir XSS
     * @param {string} text
     * @returns {string}
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Inicialización al cargar el DOM
    document.addEventListener('DOMContentLoaded', function() {
        // Headers dinámicos: delegación de eventos
        document.body.addEventListener('click', function(e) {
            // Botón "Añadir header"
            if (e.target.matches('#btn-add-header')) {
                const container = document.getElementById('headers-container');
                if (container) {
                    addHeaderRow(container);
                }
            }
            
            // Botón "Eliminar header" (delegado)
            if (e.target.matches('.btn-header-remove')) {
                removeHeaderRow(e.target);
            }
        });

        // Toggle modo avanzado
        const checkbox = document.getElementById('id_advanced_mode');
        const simpleContainer = document.getElementById('fieldset-estructurado');
        const jsonContainer = document.getElementById('fieldset-avanzado');
        const errorDiv = document.getElementById('json-error');
        
        if (checkbox && simpleContainer && jsonContainer) {
            // Exponer globalmente para compatibilidad con inline script en template
            window.toggleAdvancedMode = function(cb, simple, json, err) {
                toggleAdvancedMode(cb, simple, json, err);
            };
            
            checkbox.addEventListener('change', function() {
                toggleAdvancedMode(checkbox, simpleContainer, jsonContainer, errorDiv);
            });
        }
    });

    // Exponer funciones globalmente para tests o uso externo
    window.PanelTools = {
        addHeaderRow: addHeaderRow,
        removeHeaderRow: removeHeaderRow,
        toggleAdvancedMode: toggleAdvancedMode,
    };

    /**
     * Descubre tablas de Supabase al cambiar la credencial seleccionada.
     * @param {HTMLSelectElement} credencialSelect - Select de credenciales
     * @param {HTMLInputElement|HTMLSelectElement} endpointField - Campo "Tabla o ruta"
     */
    function discoverTables(credencialSelect, endpointField) {
        if (!credencialSelect || !endpointField) return;

        const toolTypeInput = document.getElementById('id_tool_type');
        if (!toolTypeInput || toolTypeInput.value !== 'supabase-query') return;

        credencialSelect.addEventListener('change', async function() {
            const credencialId = credencialSelect.value;
            const originalPlaceholder = endpointField.placeholder;

            if (!credencialId) {
                // Sin credencial: restaurar input libre
                restoreInput(endpointField, originalPlaceholder);
                return;
            }

            // Mostrar estado de carga
            endpointField.disabled = true;
            endpointField.placeholder = 'Cargando tablas...';

            try {
                const url = `/panel/credenciales/${credencialId}/tablas/`;
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.tables && Array.isArray(data.tables) && data.tables.length > 0) {
                        convertToSelect(endpointField, data.tables, originalPlaceholder);
                    } else {
                        restoreInput(endpointField, originalPlaceholder);
                        showHelp(endpointField, 'No se encontraron tablas. Puedes escribir el nombre a mano.');
                    }
                } else {
                    const errorData = await response.json().catch(() => ({}));
                    restoreInput(endpointField, originalPlaceholder);
                    showHelp(endpointField, errorData.error || 'No se pudo leer la lista de tablas. Puedes escribir el nombre a mano.');
                }
            } catch (err) {
                restoreInput(endpointField, originalPlaceholder);
                showHelp(endpointField, 'Error de conexión. Puedes escribir el nombre a mano.');
            }
        });
    }

    /**
     * Convierte un input en un select con opciones de tablas + "Otra (escribir a mano)"
     * @param {HTMLInputElement} input - Campo original
     * @param {string[]} tables - Lista de nombres de tabla
     * @param {string} originalPlaceholder - Placeholder original para la opción "Otra"
     */
    function convertToSelect(input, tables, originalPlaceholder) {
        const parent = input.parentElement;
        if (!parent) return;

        // Crear select
        const select = document.createElement('select');
        select.name = input.name;
        select.id = input.id;
        select.className = 'input';

        // Opción por defecto
        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = '-- Selecciona una tabla --';
        select.appendChild(defaultOpt);

        // Opciones de tablas
        tables.forEach(function(table) {
            const opt = document.createElement('option');
            opt.value = table;
            opt.textContent = table;
            select.appendChild(opt);
        });

        // Opción "Otra (escribir a mano)"
        const otherOpt = document.createElement('option');
        otherOpt.value = '__custom__';
        otherOpt.textContent = 'Otra (escribir a mano)';
        select.appendChild(otherOpt);

        // Reemplazar input por select
        parent.replaceChild(select, input);

        // Si se selecciona "Otra", volver a input
        select.addEventListener('change', function() {
            if (select.value === '__custom__') {
                restoreInput(select, originalPlaceholder);
            }
        });
    }

    /**
     * Restaura un input libre (text) en lugar del select
     * @param {HTMLSelectElement|HTMLInputElement} element - Elemento actual (select o input)
     * @param {string} placeholder - Placeholder para el input
     */
    function restoreInput(element, placeholder) {
        const parent = element.parentElement;
        if (!parent) return;

        // Si ya es input, solo actualizar placeholder
        if (element.tagName === 'INPUT') {
            element.disabled = false;
            element.placeholder = placeholder;
            removeHelp(element);
            return;
        }

        // Crear nuevo input
        const input = document.createElement('input');
        input.type = 'text';
        input.name = element.name;
        input.id = element.id;
        input.className = 'input';
        input.placeholder = placeholder;
        input.value = '';

        parent.replaceChild(input, element);
        removeHelp(input);
    }

    /**
     * Muestra un mensaje de ayuda (aviso) debajo del campo
     * @param {HTMLElement} element - Campo input/select
     * @param {string} message - Mensaje a mostrar
     */
    function showHelp(element, message) {
        removeHelp(element);
        const help = document.createElement('span');
        help.className = 'ayuda alerta-error';
        help.textContent = message;
        element.parentElement.appendChild(help);
    }

    /**
     * Elimina mensaje de ayuda previo si existe
     * @param {HTMLElement} element
     */
    function removeHelp(element) {
        const parent = element.parentElement;
        if (!parent) return;
        const existing = parent.querySelector('.ayuda.alerta-error');
        if (existing) existing.remove();
    }

    // Inicialización automática al cargar el DOM (delegación para compatibilidad con toggle modo avanzado)
    document.addEventListener('DOMContentLoaded', function() {
        const credencialSelect = document.querySelector('select[name="credencial"]');
        const endpointField = document.querySelector('input[name="endpoint"], select[name="endpoint"]');

        if (credencialSelect && endpointField) {
            discoverTables(credencialSelect, endpointField);
        }
    });

    // Exponer globalmente para uso externo
    window.PanelTools.discoverTables = discoverTables;
})();