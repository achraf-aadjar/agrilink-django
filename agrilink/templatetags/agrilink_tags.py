from django import template

register = template.Library()

@register.filter
def fcfa(amount):
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return str(amount)
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M FCFA"
    if amount >= 1_000:
        formatted = f"{amount:,}".replace(',', ' ')
        return f"{formatted} FCFA"
    return f"{amount} FCFA"

@register.filter
def pct_of(value, total):
    try:
        return round((int(value) / int(total)) * 100)
    except (ZeroDivisionError, TypeError):
        return 0

@register.filter
def abs_value(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return value
