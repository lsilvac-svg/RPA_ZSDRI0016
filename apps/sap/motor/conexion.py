"""Apertura, login y cierre de sesiones SAP GUI."""
import subprocess
import time
from pathlib import Path

from .errores import ErrorFatal, ErrorSAP
from .parametros import ParametrosConexion
from .sesion import SesionSAP
from .windows import exigir_windows, pywintypes, win32com, winreg

__all__ = ["ConectorSAP", "ParametrosConexion", "desactivar_avisos_scripting"]

CAMPO_USUARIO = "wnd[0]/usr/txtRSYST-BNAME"
CAMPO_CLAVE = "wnd[0]/usr/pwdRSYST-BCODE"
CAMPO_CLAVE_NUEVA = "wnd[1]/usr/pwdRSYST-NCODE"
# "Continuar y finalizar entradas existentes" (OPT3 = cancelar, por defecto)
OPCION_MULTI_LOGON = "wnd[1]/usr/radMULTI_LOGON_OPT1"

CLAVE_REGISTRO_SEGURIDAD = r"Software\SAP\SAPGUI Front\SAP Frontend Server\Security"


class ConectorSAP:
    """Entrega una sesión SAP lista para trabajar y la cierra al final.

    - Si el usuario ya tiene una conexión abierta en este equipo, abre un
      modo nuevo en ella (sin login ni aviso de entrada múltiple) y al
      terminar cierra solo ese modo.
    - Si no, abre una conexión nueva, inicia sesión y al terminar cierra
      la conexión completa (logout) para no bloquear el usuario.

    Uso:
        with ConectorSAP(parametros, log) as sesion:
            ...
    """

    def __init__(self, parametros, log):
        self.p = parametros
        self.log = log
        self._connection = None
        self._sesion = None
        self._conexion_propia = False

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *exc):
        self.cerrar()
        return False

    # --- Apertura ------------------------------------------------------

    def abrir(self):
        exigir_windows()
        application = self._motor_scripting()
        usuario = self.p.usuario.upper()

        connection = self._conexion_existente(application, usuario)
        if connection is not None:
            sesion = self._crear_modo(connection)
            if sesion is not None:
                self._connection, self._sesion = connection, sesion
                return sesion

        self.log.info("Abriendo conexión '%s'", self.p.conexion_logon)
        try:
            connection = application.OpenConnection(self.p.conexion_logon, True)
        except pywintypes.com_error:
            raise ErrorSAP(
                f"No se pudo abrir la conexión '{self.p.conexion_logon}' "
                "de SAP Logon"
            )

        self._connection = connection
        self._conexion_propia = True
        self._sesion = SesionSAP(connection.Children(0), self.p.tiempo_espera)
        self._sesion.esperar()
        self._iniciar_sesion(self._sesion, usuario)
        return self._sesion

    def _motor_scripting(self):
        avisos_cambiados = desactivar_avisos_scripting()
        if avisos_cambiados:
            self.log.info("Avisos de scripting de SAP GUI desactivados")

        try:
            sap_gui = win32com.client.GetObject("SAPGUI")
            if avisos_cambiados:
                self.log.warning(
                    "SAP Logon ya estaba abierto: puede mostrar el aviso de "
                    "scripting una última vez hasta que se reinicie"
                )
        except pywintypes.com_error:
            sap_gui = self._iniciar_saplogon()

        try:
            application = sap_gui.GetScriptingEngine
        except pywintypes.com_error:
            raise ErrorFatal(
                "SAP GUI rechazó el acceso del script (se pulsó Cancelar en "
                "el aviso de scripting o el scripting está bloqueado)"
            )
        if application is None:
            raise ErrorFatal("SAP GUI Scripting no está habilitado")
        return application

    def _iniciar_saplogon(self):
        if not Path(self.p.ruta_saplogon).exists():
            raise ErrorFatal(f"No se encontró SAP Logon en {self.p.ruta_saplogon}")

        self.log.info("Iniciando SAP Logon")
        subprocess.Popen(self.p.ruta_saplogon)
        limite = time.monotonic() + self.p.tiempo_inicio_saplogon

        while time.monotonic() < limite:
            time.sleep(1)
            try:
                return win32com.client.GetObject("SAPGUI")
            except pywintypes.com_error:
                pass
        raise ErrorSAP("SAP Logon no respondió a tiempo")

    def _conexion_existente(self, application, usuario):
        for i in range(application.Children.Count):
            connection = application.Children(i)
            if connection.Description != self.p.conexion_logon:
                continue
            for j in range(connection.Children.Count):
                try:
                    if connection.Children(j).Info.User.upper() == usuario:
                        return connection
                except pywintypes.com_error:
                    continue  # sesión ocupada o cerrándose
        return None

    def _crear_modo(self, connection):
        antes = connection.Children.Count
        try:
            connection.Children(0).CreateSession()
        except pywintypes.com_error:
            self.log.warning("No se pudo crear un modo nuevo (¿límite de ventanas?)")
            return None

        limite = time.monotonic() + self.p.tiempo_espera
        while connection.Children.Count <= antes:
            if time.monotonic() > limite:
                self.log.warning("El modo nuevo no apareció a tiempo")
                return None
            time.sleep(0.5)

        sesion = SesionSAP(
            connection.Children(connection.Children.Count - 1),
            self.p.tiempo_espera,
        )
        sesion.esperar()
        sesion.maximizar()
        self.log.info(
            "Se reutiliza la conexión abierta de %s en un modo nuevo",
            sesion.usuario,
        )
        return sesion

    def _iniciar_sesion(self, sesion, usuario):
        self.log.info("Iniciando sesión con el usuario %s", usuario)
        sesion.maximizar()
        sesion.escribir(CAMPO_USUARIO, usuario)
        sesion.escribir(CAMPO_CLAVE, self.p.clave)
        sesion.tecla(0)
        sesion.esperar()

        # Ventanas posteriores al login: entrada múltiple, avisos
        for _ in range(5):
            if not sesion.existe("wnd[1]"):
                break
            if sesion.existe(CAMPO_CLAVE_NUEVA):
                raise ErrorFatal(
                    "SAP solicita cambiar la contraseña. Cambiarla manualmente "
                    "y actualizarla en Conexiones SAP"
                )
            if sesion.existe(OPCION_MULTI_LOGON):
                self._resolver_entrada_multiple(sesion, usuario)
            else:
                self.log.info("Aviso al iniciar sesión: %s", sesion.texto_ventana())
            sesion.tecla(0, "wnd[1]")
            sesion.esperar()
        else:
            raise ErrorSAP("Ventana emergente inesperada después del login")

        # Sigue en la pantalla de login: acceso rechazado. No se reintenta
        # para no bloquear el usuario por intentos fallidos.
        if sesion.existe(CAMPO_USUARIO):
            _, texto = sesion.barra_estado()
            raise ErrorFatal(f"No se pudo iniciar sesión: {texto}")

        self.log.info("Sesión iniciada en %s", sesion.sistema)

    def _resolver_entrada_multiple(self, sesion, usuario):
        # El usuario tiene sesión en otro equipo; la opción por defecto
        # de SAP es cancelar, por eso se elige explícitamente.
        detalle = sesion.texto_ventana()
        if not self.p.finalizar_otras_sesiones:
            raise ErrorFatal(
                f"{usuario} ya tiene una sesión abierta en otro equipo "
                f"({detalle}). Cerrarla o activar 'Finalizar otras sesiones' "
                "en la conexión SAP"
            )
        self.log.warning("Se finalizan las otras sesiones de %s: %s", usuario, detalle)
        sesion.com.findById(OPCION_MULTI_LOGON).select()

    # --- Cierre --------------------------------------------------------

    def cerrar(self):
        if self._connection is None:
            return
        try:
            if self._conexion_propia:
                self._connection.CloseConnection()
                self.log.info("Sesión SAP cerrada")
            else:
                # Solo el modo del robot; la conexión del usuario sigue abierta
                self._sesion.comando("/i")
                self.log.info("Modo del robot cerrado")
        except (pywintypes.com_error, ErrorSAP):
            self.log.warning("No se pudo cerrar la sesión SAP")
        finally:
            self._connection = None


def desactivar_avisos_scripting():
    """Desactiva "Un script está intentando acceder a SAP GUI".

    Ese aviso espera un clic y bloquea al robot. Se cambia solo para el
    usuario de Windows actual. Devuelve True si se modificó algo.
    """
    cambiado = False
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE_REGISTRO_SEGURIDAD) as reg:
        for nombre in ("WarnOnAttach", "WarnOnConnection"):
            try:
                valor, _ = winreg.QueryValueEx(reg, nombre)
            except FileNotFoundError:
                valor = 1
            if valor != 0:
                winreg.SetValueEx(reg, nombre, 0, winreg.REG_DWORD, 0)
                cambiado = True
    return cambiado
