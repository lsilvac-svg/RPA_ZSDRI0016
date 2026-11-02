"""Registro de los robots disponibles.

Cada app de RPA registra su clase con @registrar al cargarse (en el
ready() de su AppConfig).
"""
_robots = {}


def registrar(clase):
    if not clase.codigo:
        raise ValueError(f"{clase.__name__} no define 'codigo'")
    existente = _robots.get(clase.codigo)
    if existente is not None and existente is not clase:
        raise ValueError(f"Código de robot duplicado: {clase.codigo}")
    _robots[clase.codigo] = clase
    return clase


def obtener(codigo):
    try:
        return _robots[codigo]
    except KeyError:
        raise LookupError(
            f"El robot '{codigo}' no está instalado (falta su app en INSTALLED_APPS)"
        )


def todos():
    return dict(_robots)
