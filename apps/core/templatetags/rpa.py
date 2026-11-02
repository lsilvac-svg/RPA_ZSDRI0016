from django import template

register = template.Library()


@register.filter
def duracion(delta):
    """timedelta -> '1 h 05 min', '3 min 20 s' o '45 s'."""
    if delta is None:
        return "—"
    segundos = int(delta.total_seconds())
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas} h {minutos:02d} min"
    if minutos:
        return f"{minutos} min {segundos:02d} s"
    return f"{segundos} s"


@register.filter
def si_no(valor):
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return "—" if valor in (None, "") else valor
