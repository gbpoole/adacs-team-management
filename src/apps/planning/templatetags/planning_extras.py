from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiply value by arg — used for pixel positioning in the Gantt timeline."""
    return int(value) * int(arg)


@register.filter
def wks(value):
    """Format a weeks value to 1 decimal place, or return '—' if None."""
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"
