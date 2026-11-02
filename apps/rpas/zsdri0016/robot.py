"""Reporte SD-FI de Venta Unidades Repuestos y Servicios (ZSDRI0016).

Ejecuta el reporte para un periodo, aplica una variante ALV y lo exporta a
Excel en una carpeta (normalmente compartida).
"""
from pathlib import Path

from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos
from apps.sap.motor import alv, archivos, fechas

# IDs de pantalla propios de este reporte
ARBOL_MENU = "wnd[0]/usr/cntlIMAGE_CONTAINER/shellcont/shell/shellcont[0]/shell"
CAMPO_FECHA_DESDE = "wnd[0]/usr/ctxtS_BUDAT-LOW"
CAMPO_FECHA_HASTA = "wnd[0]/usr/ctxtS_BUDAT-HIGH"
CAMPO_TIPO_MATERIAL = "wnd[0]/usr/ctxtS_MTART-LOW"
BOTON_VARIANTES = "wnd[0]/tbar[1]/btn[33]"
MENU_EXPORTAR = "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"


@registrar
class RobotZSDRI0016(RobotSAP):
    codigo = "ZSDRI0016"
    nombre = "Ventas ZSDRI0016"
    descripcion = (
        "Reporte SD-FI de Venta Unidades Repuestos y Servicios. Exporta el "
        "periodo a Excel con la variante ALV configurada."
    )

    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA,
                  defecto=r"Z:\Ventas 2026\Descarga_Ventas", requerido=True,
                  ayuda="Unidad de red o ruta UNC donde se guarda el Excel."),
        Parametro("nombre_reporte", "Prefijo del archivo", defecto="Reporte_ZSDRI0016",
                  requerido=True, ayuda="Se agrega el periodo: _AAAAMM o _AAAAMMDD-AAAAMMDD."),
        Parametro("variante_alv", "Variante ALV",
                  ayuda="Nombre o descripción. Vacío = usar la fila indicada abajo."),
        Parametro("fila_variante_alv", "Fila de la variante (si no se indica nombre)",
                  Tipo.ENTERO, defecto=5, minimo=0),
        Parametro("transaccion", "Transacción", defecto="ZSDRI0016",
                  ayuda="Se intenta primero; si falla se busca en el menú SAP."),
        Parametro("texto_menu", "Texto a buscar en el menú SAP", defecto="ZSDRI0016"),
        Parametro("nodo_favorito", "Nodo de favoritos (último recurso)", defecto="F00007"),
        Parametro("tiempo_ejecucion_reporte", "Tiempo máximo del reporte (s)",
                  Tipo.ENTERO, defecto=600, minimo=30),
        Parametro("abrir_excel", "Permitir que SAP abra el Excel", Tipo.BOOLEANO, defecto=True),
        Parametro("cerrar_excel", "Cerrar el Excel al terminar", Tipo.BOOLEANO, defecto=True),
        Parametro("tiempo_espera_excel", "Espera para cerrar Excel (s)",
                  Tipo.ENTERO, defecto=60, minimo=0),
    )

    parametros_ejecucion = (
        Parametro("fecha_desde", "Fecha desde", Tipo.FECHA,
                  ayuda="Vacío = primer día del mes anterior."),
        Parametro("fecha_hasta", "Fecha hasta", Tipo.FECHA,
                  ayuda="Vacío = último día del mes anterior."),
    )

    def carpetas_autorizadas(self, config):
        return [config["carpeta_exportacion"]]

    def permitir_abrir_archivos(self, config):
        return config["abrir_excel"]

    # --- Proceso -------------------------------------------------------

    def ejecutar(self, ctx):
        desde, hasta = self._periodo(ctx.parametros)
        ctx.log.info("Periodo: %s - %s", fechas.a_sap(desde), fechas.a_sap(hasta))
        sesion, config = ctx.sesion, ctx.config

        ctx.paso("Abrir reporte", lambda: self._abrir_reporte(ctx))
        ctx.paso("Ingresar fecha inicial",
                 lambda: sesion.escribir(CAMPO_FECHA_DESDE, fechas.a_sap(desde)))
        ctx.paso("Ingresar fecha final",
                 lambda: sesion.escribir(CAMPO_FECHA_HASTA, fechas.a_sap(hasta)))
        ctx.paso("Limpiar tipo de material",
                 lambda: sesion.escribir(CAMPO_TIPO_MATERIAL, ""))
        ctx.paso("Ejecutar reporte",
                 lambda: self._ejecutar_reporte(ctx, config["tiempo_ejecucion_reporte"]))

        ctx.paso("Abrir variantes ALV", lambda: sesion.presionar(BOTON_VARIANTES))
        ctx.paso("Seleccionar variante", lambda: alv.seleccionar_variante(
            sesion, ctx.log, config["variante_alv"], config["fila_variante_alv"]
        ))

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

    def _abrir_reporte(self, ctx):
        config = ctx.config
        if config["transaccion"] and self._abrir_por_transaccion(ctx):
            return
        if self._abrir_por_menu(ctx):
            return
        raise ErrorFatal(
            "No se pudo abrir el reporte por transacción, menú ni favorito. "
            "Revisar la configuración del robot"
        )

    def _abrir_por_transaccion(self, ctx):
        sesion, transaccion = ctx.sesion, ctx.config["transaccion"]
        ctx.log.info("Abriendo transacción %s", transaccion)
        sesion.comando(f"/n{transaccion}")
        if sesion.existe(CAMPO_FECHA_DESDE):
            return True

        _, texto = sesion.barra_estado()
        ctx.log.warning("La transacción %s no abrió el reporte (%s)", transaccion, texto)
        sesion.comando("/n")
        return False

    def _abrir_por_menu(self, ctx):
        sesion, config = ctx.sesion, ctx.config
        arbol = sesion.com.findById(ARBOL_MENU, False)
        if arbol is None:
            ctx.log.warning("No se encontró el árbol del menú SAP")
            return False

        claves = [config["nodo_favorito"]] if config["nodo_favorito"] else []
        buscado = (config["texto_menu"] or "").upper()
        if buscado:
            todas = arbol.GetAllNodeKeys()
            for i in range(todas.Count):
                clave = todas.ElementAt(i)
                if buscado in arbol.GetNodeTextByKey(clave).upper():
                    claves.insert(0, clave)
                    break

        for clave in claves:
            try:
                ctx.log.info("Abriendo nodo del menú %s", clave)
                arbol.doubleClickNode(clave)
            except Exception:
                ctx.log.warning("El nodo %s no existe en el menú", clave)
                continue
            sesion.esperar()
            if sesion.existe(CAMPO_FECHA_DESDE):
                return True
        return False

    def _ejecutar_reporte(self, ctx, tiempo_maximo):
        sesion = ctx.sesion
        sesion.tecla(8)
        sesion.esperar(tiempo_maximo)

        # Mensaje emergente (p. ej. "no se encontraron datos")
        if sesion.existe("wnd[1]") and not sesion.existe(alv.GRID_VARIANTES):
            ctx.log.info("Ventana tras ejecutar: %s", sesion.texto_ventana())
            sesion.tecla(0, "wnd[1]")
            sesion.esperar()

        # Si sigue en la pantalla de selección, no hubo resultados
        if sesion.existe(CAMPO_FECHA_DESDE):
            tipo, texto = sesion.barra_estado()
            if tipo in ("E", "A"):
                raise ErrorSAP(f"SAP respondió: {texto}")
            raise SinDatos(texto or "El reporte no devolvió datos")
