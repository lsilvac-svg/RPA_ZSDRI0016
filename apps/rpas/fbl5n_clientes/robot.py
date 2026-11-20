"""Partidas de clientes (FBL5N).

Ejecuta la FBL5N con operaciones CME y partidas memo para una sociedad,
aplica la variante de disposición y exporta a Excel (xlsx) con un nombre fijo.

La grabación original hacía dos descargas; solo la segunda (Lista →
Exportar → Hoja de cálculo, formato xlsx-TT) funciona y es la que se usa.
"""
from datetime import date

from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos, alv, archivos, fechas
from apps.sap.motor.windows import pywintypes

# IDs de pantalla de la FBL5N (pantalla de selección RFITEMAR)
CAMPO_SOCIEDAD = "wnd[0]/usr/ctxtDD_BUKRS-LOW"
CAMPO_FECHA_CLAVE = "wnd[0]/usr/ctxtPA_STIDA"
CAMPO_VARIANTE = "wnd[0]/usr/ctxtPA_VARI"
CHECK_OPERACIONES_CME = "wnd[0]/usr/chkX_SHBV"
CHECK_PARTIDAS_MEMO = "wnd[0]/usr/chkX_MERK"
MENU_EXPORTAR = "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"
COMBO_FORMATO = (
    "wnd[1]/usr/subSUB_CONFIGURATION:SAPLSALV_GUI_CUL_EXPORT_AS:0512/"
    "cmbGS_EXPORT-FORMAT"
)
FORMATO_XLSX = "xlsx-TT"


@registrar
class RobotFbl5nClientes(RobotSAP):
    codigo = "FBL5N_CLIENTES"
    nombre = "Partidas de clientes FBL5N"
    descripcion = (
        "Partidas de clientes (FBL5N) con operaciones CME y partidas memo de la "
        "sociedad configurada. Exporta a Excel con nombre fijo (Archivo_FBL5N)."
    )

    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA,
                  defecto=r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP",
                  requerido=True,
                  ayuda="Unidad de red o ruta UNC donde se guarda el Excel."),
        Parametro("nombre_reporte", "Nombre del archivo", defecto="Archivo_FBL5N",
                  requerido=True, ayuda="Sin extensión. Cada ejecución reemplaza el archivo."),
        Parametro("sociedad", "Sociedad", defecto="PE01", requerido=True),
        Parametro("operaciones_cme", "Incluir operaciones CME", Tipo.BOOLEANO, defecto=True),
        Parametro("partidas_memo", "Incluir partidas memo", Tipo.BOOLEANO, defecto=True),
        Parametro("variante", "Variante de disposición", defecto="/CXC EDWIN",
                  requerido=True,
                  ayuda="Nombre exacto de la variante en SAP, p. ej. /CXC EDWIN."),
        Parametro("tiempo_ejecucion_reporte", "Tiempo máximo del reporte (s)",
                  Tipo.ENTERO, defecto=900, minimo=30),
        Parametro("abrir_excel", "Permitir que SAP abra el Excel", Tipo.BOOLEANO, defecto=True),
        Parametro("cerrar_excel", "Cerrar el Excel al terminar", Tipo.BOOLEANO, defecto=True),
        Parametro("tiempo_espera_excel", "Espera para cerrar Excel (s)",
                  Tipo.ENTERO, defecto=60, minimo=0),
    )

    parametros_ejecucion = (
        Parametro("fecha_clave", "Fecha clave (abiertas a)", Tipo.FECHA,
                  ayuda="Vacío = hoy."),
    )

    def carpetas_autorizadas(self, config):
        return [config["carpeta_exportacion"]]

    def permitir_abrir_archivos(self, config):
        return config["abrir_excel"]

    # --- Proceso -------------------------------------------------------

    def ejecutar(self, ctx):
        sesion, config = ctx.sesion, ctx.config
        fecha_clave = ctx.parametros.get("fecha_clave") or date.today()
        ctx.log.info("Sociedad %s, fecha clave %s", config["sociedad"], fechas.a_sap(fecha_clave))

        ctx.paso("Abrir transacción FBL5N", lambda: self._abrir_transaccion(sesion))
        ctx.paso("Marcar opciones de partidas", lambda: self._marcar_opciones(sesion, config))
        ctx.paso("Ingresar sociedad",
                 lambda: sesion.escribir(CAMPO_SOCIEDAD, config["sociedad"].strip()))
        ctx.paso("Ingresar fecha clave",
                 lambda: sesion.escribir(CAMPO_FECHA_CLAVE, fechas.a_sap(fecha_clave)))
        variante = config["variante"].strip()
        ctx.paso(f"Ingresar variante de disposición '{variante}'",
                 lambda: sesion.escribir(CAMPO_VARIANTE, variante))
        ctx.paso("Ejecutar reporte",
                 lambda: self._ejecutar_reporte(ctx, config["tiempo_ejecucion_reporte"]))

        ctx.paso("Abrir exportación", lambda: sesion.seleccionar_menu(MENU_EXPORTAR))
        ctx.paso("Elegir formato Excel (xlsx)", lambda: self._formato_xlsx(sesion))
        destino = alv.exportar_excel(
            sesion, ctx.log, config["carpeta_exportacion"], config["nombre_reporte"].strip(),
            ctx.paso, tiempo_verificacion=sesion.tiempo_espera,
        )

        if config["abrir_excel"] and config["cerrar_excel"]:
            archivos.cerrar_excel(destino, config["tiempo_espera_excel"], ctx.log)

        return Resultado(mensaje=f"Reporte exportado en {destino}", archivo=str(destino))

    @staticmethod
    def _abrir_transaccion(sesion):
        sesion.comando("/nFBL5N")
        if not sesion.existe(CAMPO_SOCIEDAD):
            _, texto = sesion.barra_estado()
            raise ErrorFatal(f"No se pudo abrir la FBL5N: {texto or 'sin autorización'}")

    @staticmethod
    def _marcar_opciones(sesion, config):
        sesion.elemento(CHECK_OPERACIONES_CME).selected = config["operaciones_cme"]
        sesion.elemento(CHECK_PARTIDAS_MEMO).selected = config["partidas_memo"]

    def _ejecutar_reporte(self, ctx, tiempo_maximo):
        sesion = ctx.sesion
        sesion.tecla(8)
        sesion.esperar(tiempo_maximo)

        if sesion.existe("wnd[1]"):
            ctx.log.info("Ventana tras ejecutar: %s", sesion.texto_ventana())
            sesion.tecla(0, "wnd[1]")
            sesion.esperar(tiempo_maximo)

        # Si sigue en la pantalla de selección, hubo error o no hubo partidas
        if sesion.existe(CAMPO_SOCIEDAD):
            tipo, texto = sesion.barra_estado()
            if tipo in ("E", "A"):
                raise ErrorSAP(f"SAP respondió: {texto}")
            raise SinDatos(texto or "La FBL5N no devolvió partidas")

    @staticmethod
    def _formato_xlsx(sesion):
        combo = sesion.elemento(COMBO_FORMATO)
        try:
            combo.key = FORMATO_XLSX
        except pywintypes.com_error:
            raise ErrorFatal(f"SAP no ofrece el formato de exportación {FORMATO_XLSX}")
