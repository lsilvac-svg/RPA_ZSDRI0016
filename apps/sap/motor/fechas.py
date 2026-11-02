"""Fechas en el formato que esperan las pantallas SAP."""
from datetime import date, timedelta

FORMATO_SAP = "%d.%m.%Y"


def mes_anterior(hoy=None):
    """(primer día, último día) del mes anterior a `hoy`."""
    hoy = hoy or date.today()
    fin = hoy.replace(day=1) - timedelta(days=1)
    return fin.replace(day=1), fin


def a_sap(fecha):
    return fecha.strftime(FORMATO_SAP)


def es_mes_completo(inicio, fin):
    return (
        inicio.day == 1
        and (fin + timedelta(days=1)).day == 1
        and (inicio.year, inicio.month) == (fin.year, fin.month)
    )


def sufijo_periodo(inicio, fin):
    """'AAAAMM' para un mes completo; 'AAAAMMDD-AAAAMMDD' en otro caso."""
    if es_mes_completo(inicio, fin):
        return f"{inicio:%Y%m}"
    return f"{inicio:%Y%m%d}-{fin:%Y%m%d}"
