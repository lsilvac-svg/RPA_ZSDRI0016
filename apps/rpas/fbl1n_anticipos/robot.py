"""Anticipos a proveedores (FBL1N).

Ejecuta la FBL1N con operaciones CME (anticipos) y partidas memo para una
sociedad, aplica la variante de disposición y exporta a Excel (xlsx).
"""
from datetime import date

from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos
from apps.sap.motor import alv, archivos, fechas
from apps.sap.motor.windows import pywintypes

# IDs de pantalla de la FBL1N (pantalla de selección RFITEMAP)
CAMPO_SOCIEDAD = "wnd[0]/usr/ctxtKD_BUKRS-LOW"
CAMPO_FECHA_CLAVE = "wnd[0]/usr/ctxtPA_STIDA"
CAMPO_VARIANTE = "wnd[0]/usr/ctxtPA_VARI"
CHECK_OPERACIONES_CME = "wnd[0]/usr/chkX_SHBV"
CHECK_PARTIDAS_MEMO = "wnd[0]/usr/chkX_MERK"
LISTA_VARIANTES = "wnd[1]/usr"
MENU_EXPORTAR = "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"
COMBO_FORMATO = (
    "wnd[1]/usr/subSUB_CONFIGURATION:SAPLSALV_GUI_CUL_EXPORT_AS:0512/"
    "cmbGS_EXPORT-FORMAT"
)
FORMATO_XLSX = "xlsx-TT"


@registrar
class RobotFbl1nAnticipos(RobotSAP):
    codigo = "FBL1N_ANTICIPOS"
    nombre = "Anticipos FBL1N"
    descripcion = (
        "Partidas de proveedores (FBL1N) con operaciones CME y partidas memo "
        "de la sociedad configurada. Exporta a Excel con la variante indicada."
    )

    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA,
                  defecto=r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP",
                  requerido=True,
                  ayuda="Unidad de red o ruta UNC donde se guarda el Excel."),
        Parametro("nombre_reporte", "Nombre del archivo", defecto="Anticipos_FBL1N_2026",
                  requerido=True, ayuda="Sin extensión. Cada ejecución reemplaza el archivo."),
        Parametro("fecha_en_nombre", "Agregar la fecha clave al nombre (_AAAAMMDD)",
                  Tipo.BOOLEANO, defecto=False,
                  ayuda="Desmarcado = un solo archivo que se reemplaza en cada ejecución."),
        Parametro("sociedad", "Sociedad", defecto="PE01", requerido=True),
        Parametro("variante", "Variante de disposición",
                  ayuda="Nombre de la variante, p. ej. /ANTICIPOS. Vacío = elegirla "
                        "en la lista F4 por la posición de abajo (frágil)."),
        Parametro("posicion_lista_variantes", "Posición de la barra en la lista F4",
                  Tipo.ENTERO, defecto=14, minimo=0,
                  ayuda="Solo si no se indica el nombre de la variante."),
        Parametro("fila_lista_variantes", "Fila en la lista F4", Tipo.ENTERO,
                  defecto=20, minimo=0,
                  ayuda="Solo si no se indica el nombre de la variante."),
        Parametro("tiempo_ejecucion_reporte", "Tiempo máximo del reporte (s)",
                  Tipo.ENTERO, defecto=600, minimo=30),
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

        ctx.paso("Abrir transacción FBL1N", lambda: self._abrir_transaccion(sesion))
        ctx.paso("Marcar operaciones CME y partidas memo", lambda: self._marcar_opciones(sesion))
        ctx.paso("Ingresar sociedad", lambda: sesion.escribir(CAMPO_SOCIEDAD, config["sociedad"]))
        ctx.paso("Ingresar fecha clave",
                 lambda: sesion.escribir(CAMPO_FECHA_CLAVE, fechas.a_sap(fecha_clave)))
        ctx.paso("Seleccionar variante de disposición", lambda: self._variante(ctx))
        ctx.paso("Ejecutar reporte",
                 lambda: self._ejecutar_reporte(ctx, config["tiempo_ejecucion_reporte"]))

        ctx.paso("Abrir exportación", lambda: sesion.seleccionar_menu(MENU_EXPORTAR))
        ctx.paso("Elegir formato Excel (xlsx)", lambda: self._formato_xlsx(sesion))
        nombre = config["nombre_reporte"]
        if config["fecha_en_nombre"]:
            nombre = f"{nombre}_{fecha_clave:%Y%m%d}"
        destino = alv.exportar_excel(
            sesion, ctx.log, config["carpeta_exportacion"], nombre, ctx.paso,
            tiempo_verificacion=sesion.tiempo_espera,
        )

        if config["abrir_excel"] and config["cerrar_excel"]:
            archivos.cerrar_excel(destino, config["tiempo_espera_excel"], ctx.log)

        return Resultado(mensaje=f"Reporte exportado en {destino}", archivo=str(destino))

    @staticmethod
    def _abrir_transaccion(sesion):
        sesion.comando("/nFBL1N")
        if not sesion.existe(CAMPO_SOCIEDAD):
            _, texto = sesion.barra_estado()
            raise ErrorFatal(f"No se pudo abrir la FBL1N: {texto or 'sin autorización'}")

    @staticmethod
    def _marcar_opciones(sesion):
        sesion.elemento(CHECK_OPERACIONES_CME).selected = True
        sesion.elemento(CHECK_PARTIDAS_MEMO).selected = True

    def _variante(self, ctx):
        sesion, config = ctx.sesion, ctx.config
        nombre = (config["variante"] or "").strip()
        if nombre:
            sesion.escribir(CAMPO_VARIANTE, nombre)
            return

        # Sin nombre: se repite la selección grabada en la lista F4
        ctx.log.warning(
            "No hay nombre de variante configurado; se elige por posición en la lista F4"
        )
        sesion.elemento(CAMPO_VARIANTE).setFocus()
        sesion.tecla(4)
        sesion.esperar()
        lista = sesion.elemento(LISTA_VARIANTES)
        lista.verticalScrollbar.position = config["posicion_lista_variantes"]
        sesion.esperar()

        etiqueta = sesion.com.findById(
            f"{LISTA_VARIANTES}/lbl[1,{config['fila_lista_variantes']}]", False
        )
        if etiqueta is None:
            sesion.tecla(12, "wnd[1]")
            raise ErrorFatal(
                "No se encontró la variante en la lista F4. Indicar su nombre en "
                "Robots → Configurar"
            )
        ctx.log.info("Variante elegida en la lista: %s", etiqueta.Text.strip())
        etiqueta.setFocus()
        sesion.tecla(2, "wnd[1]")
        sesion.esperar()

    def _ejecutar_reporte(self, ctx, tiempo_maximo):
        sesion = ctx.sesion
        sesion.tecla(8)
        sesion.esperar(tiempo_maximo)

        if sesion.existe("wnd[1]"):
            ctx.log.info("Ventana tras ejecutar: %s", sesion.texto_ventana())
            sesion.tecla(0, "wnd[1]")
            sesion.esperar()

        # Si sigue en la pantalla de selección, no hubo partidas
        if sesion.existe(CAMPO_SOCIEDAD):
            tipo, texto = sesion.barra_estado()
            if tipo in ("E", "A"):
                raise ErrorSAP(f"SAP respondió: {texto}")
            raise SinDatos(texto or "La FBL1N no devolvió partidas")

    @staticmethod
    def _formato_xlsx(sesion):
        combo = sesion.elemento(COMBO_FORMATO)
        try:
            combo.key = FORMATO_XLSX
        except pywintypes.com_error:
            raise ErrorFatal(f"SAP no ofrece el formato de exportación {FORMATO_XLSX}")
