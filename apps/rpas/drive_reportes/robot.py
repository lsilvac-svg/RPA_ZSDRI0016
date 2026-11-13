"""Sube a Google Drive los Excel que generan los robots de SAP.

- Proveedores (LISTA_PROVEEDORES): se actualiza una hoja de Google Sheets
  histórica, fila por fila según una clave. Las filas que ya no vienen se
  conservan.
- Reporte SAP (REPORTE_SAP): se reemplaza por completo un archivo .xlsx de
  nombre fijo en una carpeta de Drive (mismo enlace).

No abre SAP.
"""
from datetime import datetime
from pathlib import Path

from django.utils import timezone

from apps.integraciones.google_api import ClienteGoogle, extraer_id
from apps.integraciones.models import CuentaGoogle
from apps.integraciones.tablas import fusionar, leer_excel
from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos

BASE_Y = r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO"


@registrar
class RobotDriveReportes(RobotSAP):
    codigo = "DRIVE_REPORTES"
    nombre = "Subir reportes a Drive"
    descripcion = (
        "Actualiza en Google Sheets el histórico de proveedores (LISTA_PROVEEDORES) "
        "y reemplaza en Drive el Excel del reporte SAP (REPORTE_SAP)."
    )
    requiere_sap = False

    parametros_config = (
        Parametro("cuenta_google", "Cuenta de Google",
                  ayuda="Nombre en 'Cuentas de Google'. Vacío = la única cuenta activa."),
        # Proveedores -> Google Sheets (actualizable)
        Parametro("subir_proveedores", "Actualizar proveedores en Google Sheets",
                  Tipo.BOOLEANO, defecto=True),
        Parametro("carpeta_proveedores", "Carpeta local de proveedores", Tipo.CARPETA,
                  defecto=rf"{BASE_Y}\LISTA_PROVEEDORES"),
        Parametro("patron_proveedores", "Archivos de proveedores", defecto="Proveedores_Ipesa_*.xlsx",
                  ayuda="Se toma el más reciente que coincida."),
        Parametro("hoja_proveedores", "Hoja de Google Sheets (URL o ID)",
                  ayuda="Compartida con la cuenta de servicio como Editor."),
        Parametro("pestana_proveedores", "Pestaña de la hoja", defecto="Proveedores"),
        Parametro("columnas_clave", "Columnas clave (separadas por coma)",
                  defecto="Organización compras, Proveedor, Sector",
                  ayuda="Identifican cada fila: si existe se actualiza, si no se agrega."),
        # Reporte SAP -> Drive (reemplazable)
        Parametro("subir_reporte_sap", "Reemplazar reporte SAP en Drive",
                  Tipo.BOOLEANO, defecto=True),
        Parametro("carpeta_reporte_sap", "Carpeta local del reporte SAP", Tipo.CARPETA,
                  defecto=rf"{BASE_Y}\REPORTE_SAP"),
        Parametro("patron_reporte_sap", "Archivos del reporte SAP", defecto="Anticipos_FBL1N_*.xlsx",
                  ayuda="Se toma el más reciente que coincida."),
        Parametro("carpeta_drive_reporte", "Carpeta de Drive del reporte (URL o ID)",
                  ayuda="De preferencia en una Unidad compartida."),
        Parametro("nombre_drive_reporte", "Nombre del archivo en Drive",
                  defecto="Anticipos_FBL1N.xlsx",
                  ayuda="Siempre el mismo, para conservar el enlace."),
    )
    parametros_ejecucion = ()

    def ejecutar(self, ctx):
        config = ctx.config
        if not config["subir_proveedores"] and not config["subir_reporte_sap"]:
            raise ErrorFatal("No hay nada que subir: ambas opciones están desactivadas")

        cliente = ctx.paso("Conectar con Google", lambda: self._cliente(ctx))
        tareas = []
        if config["subir_proveedores"]:
            tareas.append(("Proveedores", self._proveedores))
        if config["subir_reporte_sap"]:
            tareas.append(("Reporte SAP", self._reporte_sap))

        # Cada parte es independiente: un error en una no impide la otra.
        # Ambas son idempotentes, así que un reintento no duplica nada.
        mensajes, errores, sin_datos = [], [], 0
        for nombre, tarea in tareas:
            try:
                mensajes.append(tarea(ctx, cliente))
            except SinDatos as aviso:
                ctx.log.warning("%s: %s", nombre, aviso)
                mensajes.append(f"{nombre}: {aviso}")
                sin_datos += 1
            except Exception as error:
                ctx.log.error("%s: %s", nombre, error)
                errores.append((nombre, error))

        if errores:
            resumen = " | ".join(mensajes + [f"{n}: {e}" for n, e in errores])
            # Si algún error es temporal se reintenta todo (es idempotente)
            if any(not isinstance(e, ErrorFatal) for _, e in errores):
                raise ErrorSAP(resumen)
            raise ErrorFatal(resumen)
        if sin_datos == len(tareas):
            raise SinDatos(" | ".join(mensajes))
        return Resultado(mensaje=" | ".join(mensajes))

    # --- Pasos ---------------------------------------------------------

    @staticmethod
    def _cliente(ctx):
        try:
            cuenta = CuentaGoogle.elegir(ctx.config["cuenta_google"])
        except LookupError as error:
            raise ErrorFatal(str(error))
        ctx.log.info("Cuenta de Google: %s", cuenta.correo)
        return ClienteGoogle(cuenta.info_clave())

    def _proveedores(self, ctx, cliente):
        config = ctx.config
        hoja_id = extraer_id(config["hoja_proveedores"])
        if not hoja_id:
            raise ErrorFatal("Falta la hoja de Google Sheets de proveedores en Configurar")
        pestana = config["pestana_proveedores"] or "Proveedores"
        claves = [c.strip() for c in config["columnas_clave"].split(",") if c.strip()]
        if not claves:
            raise ErrorFatal("Indique al menos una columna clave para proveedores")

        ruta = self._mas_reciente(ctx, config["carpeta_proveedores"], config["patron_proveedores"])
        cabecera, filas = ctx.paso(f"Leer {ruta.name}", lambda: leer_excel(ruta))
        if not filas:
            raise SinDatos(f"{ruta.name} no tiene filas")
        ctx.log.info("%s: %s filas", ruta.name, len(filas))

        titulo = ctx.paso("Abrir hoja de Google Sheets",
                          lambda: cliente.asegurar_pestana(hoja_id, pestana))
        existentes = ctx.paso("Leer histórico", lambda: cliente.leer_valores(hoja_id, pestana))
        ctx.log.info("Histórico en '%s' / %s: %s filas", titulo, pestana, max(len(existentes) - 1, 0))

        marca = timezone.localtime().strftime("%Y-%m-%d %H:%M")
        try:
            fusion = fusionar(existentes, cabecera, filas, claves, marca)
        except ValueError as error:
            raise ErrorFatal(str(error))
        if fusion.columnas_nuevas:
            ctx.log.warning("Columnas nuevas agregadas a la hoja: %s", ", ".join(fusion.columnas_nuevas))
        if fusion.sin_clave:
            ctx.log.warning("%s filas sin valor en las columnas clave se omitieron", fusion.sin_clave)

        ctx.paso(
            f"Escribir {len(fusion.filas) - 1} filas en Google Sheets",
            lambda: cliente.escribir_valores(hoja_id, pestana, fusion.filas),
        )
        mensaje = (
            f"Proveedores: {fusion.nuevas} nuevos, {fusion.actualizadas} actualizados, "
            f"{fusion.sin_cambios} sin cambios, {fusion.conservadas} históricos conservados"
        )
        ctx.log.info(mensaje)
        return mensaje

    def _reporte_sap(self, ctx, cliente):
        config = ctx.config
        carpeta_id = extraer_id(config["carpeta_drive_reporte"])
        if not carpeta_id:
            raise ErrorFatal("Falta la carpeta de Drive del reporte SAP en Configurar")
        nombre = config["nombre_drive_reporte"] or "Anticipos_FBL1N.xlsx"

        ruta = self._mas_reciente(ctx, config["carpeta_reporte_sap"], config["patron_reporte_sap"])
        contenido = ctx.paso(f"Leer {ruta.name}", ruta.read_bytes)
        archivo, creado = ctx.paso(
            f"Subir {ruta.name} a Drive como {nombre}",
            lambda: cliente.reemplazar_archivo(carpeta_id, nombre, contenido),
        )
        accion = "creado" if creado else "reemplazado"
        mensaje = f"Reporte SAP {accion} en Drive: {nombre} ({ruta.name})"
        ctx.log.info("%s %s", mensaje, archivo.get("webViewLink", ""))
        return mensaje

    @staticmethod
    def _mas_reciente(ctx, carpeta, patron):
        carpeta = Path(carpeta)
        try:
            archivos = [
                a for a in carpeta.glob(patron or "*.xlsx")
                if a.is_file() and not a.name.startswith("~$")
            ]
        except OSError as error:
            raise ErrorSAP(f"No se puede leer {carpeta} ({error}). ¿Está conectada la unidad?")
        if not carpeta.is_dir():
            raise ErrorSAP(f"No existe la carpeta {carpeta}. ¿Está conectada la unidad?")
        if not archivos:
            raise SinDatos(f"No hay archivos '{patron}' en {carpeta}")
        ruta = max(archivos, key=lambda a: a.stat().st_mtime)
        modificado = datetime.fromtimestamp(ruta.stat().st_mtime)
        ctx.log.info("Archivo más reciente: %s (%s)", ruta.name, f"{modificado:%d/%m/%Y %H:%M}")
        return ruta
