import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def markdownify(text):
    if not text:
        return ""
    # Convertir markdown a HTML y marcar como seguro para evitar escape
    html = markdown.markdown(text, extensions=['fenced_code', 'tables'])
    return mark_safe(html)


@register.filter
def get_item(dictionary, key):
    """Permite acceder a claves de diccionario con nombre variable en templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
