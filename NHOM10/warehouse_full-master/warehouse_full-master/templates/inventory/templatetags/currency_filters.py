from django import template

register = template.Library()


@register.filter(name="vnd")
def format_vnd(value):
    if value is None or value == "":
        return "0 đ"
    try:
        num = int(round(float(value)))
        return f"{num:,} đ"
    except (ValueError, TypeError):
        return f"{value} đ"
