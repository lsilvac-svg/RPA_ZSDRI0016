"""Utilidades para archivos exportados desde SAP (carpetas de red, Excel)."""
import time

from .errores import ErrorFatal, ErrorSAP
from .windows import pywintypes, win32com


def preparar_carpeta(carpeta):
    # La carpeta puede estar en una unidad de red (p. ej. Z:)
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ErrorSAP(
            f"No se puede acceder a la carpeta {carpeta} ({error}). "
            "¿Está conectada la unidad de red?"
        )


def archivo_bloqueado(ruta):
    if not ruta.exists():
        return False
    try:
        with open(ruta, "r+b"):
            return False
    except PermissionError:
        return True


def liberar_archivo(ruta, log):
    """Cierra en Excel el archivo si quedó abierto; falla si sigue bloqueado."""
    if not archivo_bloqueado(ruta):
        return
    log.info("%s está abierto; se intenta cerrar en Excel", ruta.name)
    cerrar_excel(ruta, segundos=0, log=log)
    if archivo_bloqueado(ruta):
        raise ErrorFatal(
            f"{ruta} está abierto por otro programa o usuario. "
            "Cerrarlo y volver a ejecutar"
        )


def huella_archivo(ruta):
    """(fecha de modificación, tamaño) o None si no existe."""
    try:
        estado = ruta.stat()
    except OSError:
        return None
    return estado.st_mtime, estado.st_size


def esperar_archivo_nuevo(ruta, huella_previa, segundos, log):
    """Confirma en disco que el archivo se creó o reemplazó.

    Se compara con el estado previo y no con la hora local, porque en una
    carpeta de red la hora la pone el servidor.
    """
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        huella = huella_archivo(ruta)
        if huella is not None and huella[1] > 0 and huella != huella_previa:
            log.info("Archivo verificado: %s (%s KB)", ruta, huella[1] // 1024)
            return
        time.sleep(1)
    raise ErrorSAP(f"SAP no generó el archivo {ruta}")


def cerrar_excel(ruta, segundos, log):
    """Cierra en Excel el libro indicado, sin tocar otros libros abiertos.

    Excel tarda en abrir el archivo después de exportar, por eso se espera
    hasta `segundos`. Devuelve True si se cerró.
    """
    limite = time.monotonic() + segundos
    while True:
        if _cerrar_libro(ruta.name, log):
            return True
        if time.monotonic() >= limite:
            if segundos:
                log.warning("No se encontró %s abierto en Excel", ruta.name)
            return False
        time.sleep(1)


def _cerrar_libro(nombre, log):
    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
    except pywintypes.com_error:
        return False  # Excel no está abierto (todavía)

    buscado = nombre.lower()
    cerrado = False
    try:
        # Los archivos de red suelen abrirse en Vista protegida
        for i in range(excel.ProtectedViewWindows.Count, 0, -1):
            ventana = excel.ProtectedViewWindows(i)
            if ventana.SourceName.lower() == buscado:
                ventana.Close()
                cerrado = True

        for i in range(excel.Workbooks.Count, 0, -1):
            libro = excel.Workbooks(i)
            if libro.Name.lower() == buscado:
                libro.Close(SaveChanges=False)
                cerrado = True

        if cerrado:
            log.info("Excel cerrado: %s", nombre)
            # Solo se cierra Excel si no quedan otros libros del usuario
            if excel.Workbooks.Count == 0 and excel.ProtectedViewWindows.Count == 0:
                excel.Quit()
    except (pywintypes.com_error, AttributeError):
        return False  # Excel ocupado o iniciando: se reintenta

    return cerrado
