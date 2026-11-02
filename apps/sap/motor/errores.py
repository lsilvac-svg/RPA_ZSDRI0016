class ErrorSAP(Exception):
    """Error recuperable: el ejecutor reintenta el proceso completo."""


class ErrorFatal(ErrorSAP):
    """Error que no se soluciona reintentando (credenciales, configuración)."""


class SinDatos(Exception):
    """El reporte no devolvió resultados para los filtros indicados."""


class Cancelado(Exception):
    """Un usuario solicitó cancelar la ejecución desde la interfaz."""
