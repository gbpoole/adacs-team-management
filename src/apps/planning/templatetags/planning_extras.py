from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiply value by arg — used for pixel positioning in the Gantt timeline."""
    return int(value) * int(arg)
