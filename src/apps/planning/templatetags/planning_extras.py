from django import template

register = template.Library()


@register.filter
def text_colour(hex_colour):
    """Return 'white' or '#111' for legible text on the given background hex colour."""
    try:
        h = str(hex_colour).lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        def _lin(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        luminance = 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)
        return "white" if luminance < 0.179 else "#111"
    except Exception:
        return "#111"


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
