"""Clase base que implementa cada RPA de SAP.

Un robot solo describe su lógica de negocio. El framework se encarga de:
conectar e iniciar sesión, reintentos, ventana de Seguridad SAP GUI,
logs, capturas de error, cancelación y cierre de sesión.
"""
from dataclasses import dataclass

from apps.sap.motor import Cancelado


@dataclass
class Resultado:
    mensaje: str
    archivo: str = ""


class ContextoEjecucion:
    """Lo que recibe un robot al ejecutarse."""

    def __init__(self, sesion, config, parametros, log, cancelacion_solicitada):
        self.sesion = sesion
        self.config = config
        self.parametros = parametros
        self.log = log
        self._cancelacion_solicitada = cancelacion_solicitada

    def verificar_cancelacion(self):
        if self._cancelacion_solicitada():
            raise Cancelado("Ejecución cancelada por un usuario")

    def paso(self, descripcion, accion):
        """Ejecuta una acción registrándola; en SAP, valida además el resultado."""
        self.verificar_cancelacion()
        self.log.info("INICIO: %s", descripcion)
        if self.sesion is not None:
            self.sesion.esperar()
        resultado = accion()
        if self.sesion is not None:
            self.sesion.esperar()
            self.sesion.verificar_barra_estado()
        self.log.info("FIN: %s", descripcion)
        return resultado


class RobotSAP:
    """Base de todos los robots. Las subclases se registran con @registrar."""

    codigo = ""
    nombre = ""
    descripcion = ""
    # False = el robot no abre SAP (p. ej. solo mueve archivos); no necesita
    # login SAP y ctx.sesion es None
    requiere_sap = True
    # Configuración permanente (la edita un administrador)
    parametros_config = ()
    # Datos de cada ejecución (se piden al pulsar "Ejecutar")
    parametros_ejecucion = ()

    def carpetas_autorizadas(self, config):
        """Carpetas donde SAP puede escribir sin preguntar (Seguridad SAP GUI)."""
        return []

    def permitir_abrir_archivos(self, config):
        """Si se permite a SAP abrir los archivos exportados (p. ej. Excel)."""
        return False

    def ejecutar(self, ctx):
        """Lógica del robot. Debe devolver un Resultado."""
        raise NotImplementedError
