"""Motor SAP GUI Scripting reutilizable por todos los robots.

No depende de Django: recibe la configuración y un logger, de modo que
puede usarse también desde scripts o pruebas.

Módulos:
    conexion   abrir SAP Logon, login, sesión ya abierta, cierre
    sesion     esperas y acciones sobre una sesión
    seguridad  respuesta a la ventana "Seguridad SAP GUI"
    alv        variantes ALV y exportación a Excel
    archivos   carpetas de red, verificación de archivos, cerrar Excel
    fechas     periodos y formato de fecha SAP

Este paquete solo expone lo que no requiere Windows, para que la interfaz
web pueda importarlo también en Linux (Docker).
"""
from .errores import Cancelado, ErrorFatal, ErrorSAP, SinDatos
from .parametros import ParametrosConexion

__all__ = ["Cancelado", "ErrorFatal", "ErrorSAP", "ParametrosConexion", "SinDatos"]
