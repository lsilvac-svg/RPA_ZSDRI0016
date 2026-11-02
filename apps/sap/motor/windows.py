"""Librerías de Windows usadas por el motor SAP.

SAP GUI solo existe en Windows; la web, en cambio, también puede correr en
Linux (Docker). Aquí se importan una sola vez: en Linux quedan en None y
cualquier intento de operar SAP falla con un mensaje claro.
"""
try:
    import pywintypes
    import win32api
    import win32com.client
    import win32con
    import win32event
    import win32gui
    import winerror
    import winreg

    DISPONIBLE = True
except ImportError:  # Linux / Docker: solo interfaz web
    pywintypes = win32api = win32com = win32con = win32event = win32gui = None
    winerror = winreg = None
    DISPONIBLE = False


def exigir_windows():
    if not DISPONIBLE:
        raise RuntimeError(
            "El motor SAP requiere Windows con SAP GUI y pywin32. "
            "Ejecute el worker en el equipo Windows, no en Docker."
        )
