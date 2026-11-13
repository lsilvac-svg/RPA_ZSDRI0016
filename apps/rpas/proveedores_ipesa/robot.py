"""Lista de proveedores Ipesa (ZMMRI0017).

Ejecuta el reporte ZMMRI0017 para un rango de fechas de modificación
(S_AEDAT) y lo exporta a Excel.
"""
from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos
from apps.sap.motor import alv, archivos, fechas

TRANSACCION = "ZMMRI0017"
CAMPO_FECHA_DESDE = "wnd[0]/usr/ctxtS_AEDAT-LOW"
CAMPO_FECHA_HASTA = "wnd[0]/usr/ctxtS_AEDAT-HIGH"
LISTA_F4 = "wnd[1]/usr"
BOTON_ACEPTAR_F4 = "wnd[1]/tbar[0]/btn[0]"
MENU_EXPORTAR = "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"


@registrar
class RobotProveedoresIpesa(RobotSAP):
    codigo = "PROVEEDORES_IPESA"
    nombre = "Proveedores Ipesa"
    descripcion = (
        "Lista de proveedores (ZMMRI0017) modificados en un rango de fechas, "
        "exportada a Excel."
    )

    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA,
                  defecto=r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\LISTA_PROVEEDORES",
                  requerido=True,
                  ayuda="Unidad de red o ruta UNC donde se guarda el Excel."),
        Parametro("nombre_reporte", "Prefijo del archivo", defecto="Proveedores_Ipesa",
                  requerido=True, ayuda="Se agrega el periodo: _AAAAMM o _AAAAMMDD-AAAAMMDD."),
        Parametro("valor_campo_inicial", "Valor del primer campo",
                  ayuda="Valor que se escribe en el campo donde está el cursor al abrir "
                        "ZMMRI0017. Vacío = elegirlo en la lista F4 por la fila de abajo."),
        Parametro("fila_lista_campo_inicial", "Fila en la lista F4 del primer campo",
                  Tipo.ENTERO, defecto=4, minimo=0,
                  ayuda="Solo si no se indica el valor del primer campo."),
        Parametro("tiempo_ejecucion_reporte", "Tiempo máximo del reporte (s)",
                  Tipo.ENTERO, defecto=600, minimo=30),
        Parametro("abrir_excel", "Permitir que SAP abra el Excel", Tipo.BOOLEANO, defecto=True),
        Parametro("cerrar_excel", "Cerrar el Excel al terminar", Tipo.BOOLEANO, defecto=True),
        Parametro("tiempo_espera_excel", "Espera para cerrar Excel (s)",
                  Tipo.ENTERO, defecto=60, minimo=0),
    )

    parametros_ejecucion = (
        Parametro("fecha_desde", "Fecha de modificación desde", Tipo.FECHA,
                  ayuda="Vacío = primer día del mes anterior."),
        Parametro("fecha_hasta", "Fecha de modificación hasta", Tipo.FECHA,
                  ayuda="Vacío = último día del mes anterior."),
    )

    def carpetas_autorizadas(self, config):
        return [config["carpeta_exportacion"]]

    def permitir_abrir_archivos(self, config):
        return config["abrir_excel"]

    # --- Proceso -------------------------------------------------------

    def ejecutar(self, ctx):
        sesion, config = ctx.sesion, ctx.config
        desde, hasta = self._periodo(ctx.parametros)
        ctx.log.info("Periodo: %s - %s", fechas.a_sap(desde), fechas.a_sap(hasta))

        ctx.paso(f"Abrir transacción {TRANSACCION}", lambda: self._abrir_transaccion(sesion))
        ctx.paso("Completar primer campo", lambda: self._campo_inicial(ctx))
        ctx.paso("Ingresar fecha desde",
                 lambda: sesion.escribir(CAMPO_FECHA_DESDE, fechas.a_sap(desde)))
        ctx.paso("Ingresar fecha hasta",
                 lambda: sesion.escribir(CAMPO_FECHA_HASTA, fechas.a_sap(hasta)))
        ctx.paso("Ejecutar reporte",
                 lambda: self._ejecutar_reporte(ctx, config["tiempo_ejecucion_reporte"]))

        ctx.paso("Abrir exportación", lambda: sesion.seleccionar_menu(MENU_EXPORTAR))
        nombre = f"{config['nombre_reporte']}_{fechas.sufijo_periodo(desde, hasta)}"
        destino = alv.exportar_excel(
            sesion, ctx.log, config["carpeta_exportacion"], nombre, ctx.paso,
            tiempo_verificacion=sesion.tiempo_espera,
        )

        if config["abrir_excel"] and config["cerrar_excel"]:
            archivos.cerrar_excel(destino, config["tiempo_espera_excel"], ctx.log)

        return Resultado(mensaje=f"Reporte exportado en {destino}", archivo=str(destino))

    @staticmethod
    def _periodo(parametros):
        defecto_desde, defecto_hasta = fechas.mes_anterior()
        desde = parametros.get("fecha_desde") or defecto_desde
        hasta = parametros.get("fecha_hasta") or defecto_hasta
        if desde > hasta:
            raise ErrorFatal("La fecha desde no puede ser posterior a la fecha hasta")
        return desde, hasta

    @staticmethod
    def _abrir_transaccion(sesion):
        sesion.comando(f"/n{TRANSACCION}")
        if not sesion.existe(CAMPO_FECHA_DESDE):
            _, texto = sesion.barra_estado()
            raise ErrorFatal(
                f"No se pudo abrir {TRANSACCION}: {texto or 'sin autorización'}"
            )

    def _campo_inicial(self, ctx):
        """Campo donde SAP deja el cursor al abrir el reporte (el de la grabación)."""
        sesion, config = ctx.sesion, ctx.config
        campo = sesion.elemento("wnd[0]").GuiFocus
        if campo is None:
            raise ErrorFatal(f"{TRANSACCION} no dejó el cursor en ningún campo")
        id_campo = campo.Id.split("wnd[0]/", 1)[-1]

        valor = (config["valor_campo_inicial"] or "").strip()
        if valor:
            ctx.log.info("Campo %s = %s", id_campo, valor)
            campo.text = valor
            return

        sesion.tecla(4)
        sesion.esperar()
        fila = config["fila_lista_campo_inicial"]
        etiqueta = sesion.com.findById(f"{LISTA_F4}/lbl[1,{fila}]", False)
        if etiqueta is None:
            if sesion.existe("wnd[1]"):
                sesion.tecla(12, "wnd[1]")
            raise ErrorFatal(
                f"No se encontró la fila {fila} en la lista F4 del campo {id_campo}. "
                "Indicar el valor del primer campo en Robots → Configurar"
            )
        ctx.log.info("Campo %s: elegido '%s' en la lista F4", id_campo, etiqueta.Text.strip())
        etiqueta.setFocus()
        sesion.presionar(BOTON_ACEPTAR_F4)
        sesion.esperar()

    def _ejecutar_reporte(self, ctx, tiempo_maximo):
        sesion = ctx.sesion
        sesion.tecla(8)
        sesion.esperar(tiempo_maximo)

        if sesion.existe("wnd[1]"):
            ctx.log.info("Ventana tras ejecutar: %s", sesion.texto_ventana())
            sesion.tecla(0, "wnd[1]")
            sesion.esperar()

        # Si sigue en la pantalla de selección, no hubo resultados
        if sesion.existe(CAMPO_FECHA_DESDE):
            tipo, texto = sesion.barra_estado()
            if tipo in ("E", "A"):
                raise ErrorSAP(f"SAP respondió: {texto}")
            raise SinDatos(texto or "El reporte no devolvió proveedores")
