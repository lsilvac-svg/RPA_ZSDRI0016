"""Operaciones comunes sobre reportes ALV: variantes y exportación a Excel."""
from pathlib import Path

from .archivos import esperar_archivo_nuevo, huella_archivo, liberar_archivo, preparar_carpeta
from .errores import ErrorFatal, ErrorSAP
from .windows import pywintypes

GRID_VARIANTES = (
    "wnd[1]/usr/subSUB_CONFIGURATION:SAPLSALV_CUL_LAYOUT_CHOOSE:0500/"
    "cntlD500_CONTAINER/shellcont/shell"
)
# Ventana "Export As"
CAMPO_NOMBRE_EXPORTACION = (
    "wnd[1]/usr/subSUB_CONFIGURATION:SAPLSALV_GUI_CUL_EXPORT_AS:0512/"
    "txtGS_EXPORT-FILE_NAME"
)
BOTON_EXPORTAR_A = "wnd[1]/tbar[0]/btn[20]"
# Ventana "Grabar fichero"
CAMPO_DIRECTORIO = "wnd[1]/usr/ctxtDY_PATH"
CAMPO_FICHERO = "wnd[1]/usr/ctxtDY_FILENAME"
BOTON_REEMPLAZAR = "wnd[1]/tbar[0]/btn[11]"

PALABRAS_ERROR = ("denied", "denegado", "sy-subrc", "error")


def seleccionar_variante(sesion, log, nombre=None, fila_defecto=0):
    """Elige una variante en la lista de layouts ALV (ya abierta).

    Busca por nombre o descripción; si no se indica o no existe, usa la
    fila `fila_defecto`.
    """
    grid = sesion.elemento(GRID_VARIANTES)

    fila = _buscar_fila(grid, nombre) if nombre else None
    if fila is None:
        if nombre:
            log.warning("Variante '%s' no encontrada; se usa la fila %s", nombre, fila_defecto)
        fila = fila_defecto

    if fila >= grid.RowCount:
        raise ErrorFatal(f"La lista de variantes solo tiene {grid.RowCount} filas")

    log.info("Variante seleccionada: %s", grid.GetCellValue(fila, "TEXT"))
    grid.setCurrentCell(fila, "TEXT")
    grid.selectedRows = str(fila)
    grid.clickCurrentCell()


def _buscar_fila(grid, nombre):
    buscado = nombre.strip().upper()
    for fila in range(grid.RowCount):
        for columna in ("VARIANT", "TEXT"):
            try:
                valor = grid.GetCellValue(fila, columna)
            except pywintypes.com_error:
                continue
            if valor.strip().upper() == buscado:
                return fila
    return None


def exportar_excel(sesion, log, carpeta, nombre_base, paso, tiempo_verificacion=30):
    """Completa las ventanas "Export As" y "Grabar fichero" de un ALV.

    Debe llamarse con la ventana "Export As" ya abierta. Devuelve la ruta
    del archivo verificado en disco. `paso` es el ContextoEjecucion.paso
    del robot, para registrar cada acción.
    """
    carpeta = Path(carpeta)

    paso(
        f"Asignar nombre de archivo '{nombre_base}'",
        lambda: sesion.escribir(CAMPO_NOMBRE_EXPORTACION, nombre_base),
    )
    paso("Continuar exportación", lambda: sesion.presionar(BOTON_EXPORTAR_A))

    # Ventana "Grabar fichero": se fija la carpeta y el nombre final
    extension = Path(sesion.leer(CAMPO_FICHERO).strip()).suffix or ".xlsx"
    destino = carpeta / f"{nombre_base}{extension}"
    preparar_carpeta(carpeta)
    liberar_archivo(destino, log)

    def asignar_destino():
        sesion.escribir(CAMPO_DIRECTORIO, str(carpeta))
        sesion.escribir(CAMPO_FICHERO, destino.name)

    paso(f"Asignar destino '{destino}'", asignar_destino)

    huella_previa = huella_archivo(destino)
    paso("Confirmar exportación", lambda: _confirmar(sesion, log))
    esperar_archivo_nuevo(destino, huella_previa, tiempo_verificacion, log)
    return destino


def _confirmar(sesion, log):
    sesion.presionar(BOTON_REEMPLAZAR)
    sesion.esperar()

    # Mensajes posteriores: confirmaciones o errores de escritura
    for _ in range(3):
        if not sesion.existe("wnd[1]"):
            return
        texto = sesion.texto_ventana()
        if any(p in texto.lower() for p in PALABRAS_ERROR):
            raise ErrorFatal(
                f"SAP no pudo grabar el archivo: {texto}. Revisar permisos de "
                "Seguridad SAP GUI sobre la carpeta de exportación"
            )
        log.info("Confirmación de exportación: %s", texto)
        sesion.tecla(0, "wnd[1]")
        sesion.esperar()

    raise ErrorSAP(f"La exportación no se cerró: {sesion.texto_ventana()}")
