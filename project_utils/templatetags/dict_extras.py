from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    if isinstance(d, dict):
        return d.get(key)
    # Allow QueryDict or similar mapping-like objects
    try:
        return d[key]
    except Exception:
        return None
    


@register.filter
def get_attr(obj, name):
    try:
        return getattr(obj, name)
    except Exception:
        return None
