
import time
import logging
import win32com.client

# ==============================================
# CONFIGURACIÓN DEL RPA
# ==============================================

FECHA_INICIO = "01.10.2026"
FECHA_FIN = "31.10.2026"

NOMBRE_REPORTE = "Reporte_ZSDRI0016"

INDICE_CONEXION = 0
INDICE_SESION = 0

logging.basicConfig(
    filename="rpa_sap.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)


# ==============================================
# CONEXIÓN SAP
# ==============================================

def conectar_sap():
    sap_gui = win32com.client.GetObject("SAPGUI")
    application = sap_gui.GetScriptingEngine

    connection = application.Children(INDICE_CONEXION)
    session = connection.Children(INDICE_SESION)

    print("Conectado a SAP correctamente")
    return session


# ==============================================
# FUNCIONES DE CONTROL
# ==============================================

def esperar_sap(session, segundos=30):
    limite = time.monotonic() + segundos

    while session.Busy:
        if time.monotonic() > limite:
            raise TimeoutError("Tiempo de espera agotado")
        time.sleep(0.2)


def ejecutar_paso(session, descripcion, accion):
    print(f"Ejecutando: {descripcion}")
    logging.info("INICIO: %s", descripcion)

    esperar_sap(session)
    accion()
    esperar_sap(session)

    logging.info("FIN: %s", descripcion)


# ==============================================
# PROCESO PRINCIPAL
# ==============================================

def ejecutar_rpa():
    session = conectar_sap()

    try:
        # 1. Maximizar SAP
        ejecutar_paso(
            session,
            "Maximizar SAP",
            lambda: session.findById("wnd[0]").maximize()
        )

        # 2. Abrir reporte desde el menú SAP
        ejecutar_paso(
            session,
            "Abrir reporte",
            lambda: session.findById(
                "wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/"
                "shell/shellcont[0]/shell"
            ).doubleClickNode("F00007")
        )

        # 3. Ingresar fecha inicial
        ejecutar_paso(
            session,
            "Ingresar fecha inicial",
            lambda: setattr(
                session.findById(
                    "wnd[0]/usr/ctxtS_BUDAT-LOW"
                ),
                "text",
                FECHA_INICIO
            )
        )

        # 4. Ingresar fecha final
        ejecutar_paso(
            session,
            "Ingresar fecha final",
            lambda: setattr(
                session.findById(
                    "wnd[0]/usr/ctxtS_BUDAT-HIGH"
                ),
                "text",
                FECHA_FIN
            )
        )

        # 5. Limpiar filtro de tipo de material
        ejecutar_paso(
            session,
            "Limpiar tipo de material",
            lambda: setattr(
                session.findById(
                    "wnd[0]/usr/ctxtS_MTART-LOW"
                ),
                "text",
                ""
            )
        )

        # 6. Ejecutar reporte (F8)
        ejecutar_paso(
            session,
            "Ejecutar reporte",
            lambda: session.findById(
                "wnd[0]/tbar[1]/btn[8]"
            ).press()
        )

        # 7. Abrir selección de layout ALV
        ejecutar_paso(
            session,
            "Abrir variantes ALV",
            lambda: session.findById(
                "wnd[0]/tbar[1]/btn[33]"
            ).press()
        )

        # 8. Seleccionar la variante grabada
        ruta_layout = (
            "wnd[1]/usr/"
            "subSUB_CONFIGURATION:"
            "SAPLSALV_CUL_LAYOUT_CHOOSE:0500/"
            "cntlD500_CONTAINER/shellcont/shell"
        )

        grid = session.findById(ruta_layout)

        ejecutar_paso(
            session,
            "Seleccionar variante de visualización",
            lambda: seleccionar_variante(grid)
        )

        # 9. Abrir exportación
        ejecutar_paso(
            session,
            "Abrir exportación",
            lambda: session.findById(
                "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"
            ).select()
        )

        # 10. Establecer nombre del reporte
        ejecutar_paso(
            session,
            "Asignar nombre de archivo",
            lambda: setattr(
                session.findById(
                    "wnd[1]/usr/"
                    "subSUB_CONFIGURATION:"
                    "SAPLSALV_GUI_CUL_EXPORT_AS:0512/"
                    "txtGS_EXPORT-FILE_NAME"
                ),
                "text",
                NOMBRE_REPORTE
            )
        )

        # 11. Reproducir el primer botón de exportación
        ejecutar_paso(
            session,
            "Continuar exportación",
            lambda: session.findById(
                "wnd[1]/tbar[0]/btn[20]"
            ).press()
        )

        # 12. Confirmar exportación
        ejecutar_paso(
            session,
            "Confirmar exportación",
            lambda: session.findById(
                "wnd[1]/tbar[0]/btn[11]"
            ).press()
        )

        print("Secuencia SAP ejecutada.")
        logging.info("Secuencia completada")

        # Se omiten los dos botones de regresar
        # para poder inspeccionar el resultado.

    except Exception:
        logging.exception("Fallo durante el proceso SAP")
        print("Error en el RPA. Revisar rpa_sap.log")
        raise


def seleccionar_variante(grid):
    # Reproduce exactamente la fila grabada.
    # IMPORTANTE: la fila 5 puede cambiar.
    grid.setCurrentCell(5, "TEXT")
    grid.selectedRows = "5"
    grid.clickCurrentCell()


if __name__ == "__main__":
    ejecutar_rpa()
