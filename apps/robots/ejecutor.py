"""Ejecución de un robot: reintentos, estados, logs y capturas de error.

Esta lógica es común a todos los robots; cada robot solo implementa
RobotSAP.ejecutar().
"""
import logging
import time
from contextlib import contextmanager

from django.conf import settings
from django.utils import timezone

from apps.sap.motor import Cancelado, ErrorFatal, SinDatos
from apps.sap.motor.conexion import ConectorSAP
from apps.sap.motor.seguridad import VigilanteSeguridad

from . import parametros as params
from .base import ContextoEjecucion
from .models import Ejecucion, LogEjecucion

log = logging.getLogger("rpa.ejecucion")


class ManejadorLogBD(logging.Handler):
    """Guarda cada mensaje del robot en LogEjecucion (visible en la web)."""

    def __init__(self, ejecucion_id):
        super().__init__(level=logging.INFO)
        self.ejecucion_id = ejecucion_id

    def emit(self, registro):
        try:
            mensaje = self.format(registro)
            LogEjecucion.objects.create(
                ejecucion_id=self.ejecucion_id,
                nivel=registro.levelname,
                mensaje=mensaje,
            )
        except Exception:
            self.handleError(registro)


@contextmanager
def logs_en_bd(ejecucion):
    manejador = ManejadorLogBD(ejecucion.pk)
    manejador.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(manejador)
    try:
        yield
    finally:
        log.removeHandler(manejador)


def ejecutar(ejecucion):
    """Corre una ejecución PENDIENTE hasta dejarla en un estado final."""
    robot = ejecucion.robot
    _actualizar(ejecucion, estado=Ejecucion.Estado.EJECUTANDO, inicio=timezone.now())

    with logs_en_bd(ejecucion):
        log.info("===== Inicio %s (ejecución #%s) =====", robot.nombre, ejecucion.pk)
        try:
            estado, mensaje, archivo = _ejecutar_con_reintentos(ejecucion)
        except ErrorFatal as error:  # configuración incompleta
            log.error("%s", error)
            estado, mensaje, archivo = Ejecucion.Estado.FALLIDA, str(error), ""
        except Exception as error:  # error inesperado antes de iniciar
            log.exception("No se pudo iniciar la ejecución")
            estado, mensaje, archivo = Ejecucion.Estado.FALLIDA, str(error), ""

        log.info("===== Fin: %s =====", Ejecucion.Estado(estado).label)

    _actualizar(ejecucion, estado=estado, mensaje=mensaje, archivo=archivo, fin=timezone.now())


def _ejecutar_con_reintentos(ejecucion):
    robot = ejecucion.robot
    if robot.conexion is None:
        raise ErrorFatal("El robot no tiene una conexión SAP asignada")
    if not robot.conexion.activa:
        raise ErrorFatal(f"La conexión SAP '{robot.conexion}' está inactiva")

    instancia = robot.clase()
    config = robot.config_efectiva()
    valores = params.resolver(instancia.parametros_ejecucion, ejecucion.parametros)
    conexion = robot.conexion.parametros()
    intentos = max(robot.reintentos, 1)

    for intento in range(1, intentos + 1):
        _actualizar(ejecucion, intentos=intento)
        log.info("Intento %s de %s", intento, intentos)
        try:
            resultado = _intento(ejecucion, instancia, config, valores, conexion)
            return Ejecucion.Estado.EXITOSA, resultado.mensaje, resultado.archivo
        except SinDatos as aviso:
            log.warning("Sin datos: %s", aviso)
            return Ejecucion.Estado.SIN_DATOS, str(aviso), ""
        except Cancelado as aviso:
            log.warning("%s", aviso)
            return Ejecucion.Estado.CANCELADA, str(aviso), ""
        except ErrorFatal as error:
            log.error("Error que requiere revisión manual: %s", error)
            return Ejecucion.Estado.FALLIDA, str(error), ""
        except Exception as error:
            log.exception("Falló el intento %s", intento)
            if intento == intentos:
                return Ejecucion.Estado.FALLIDA, str(error), ""
            log.info("Reintentando en %s segundos", robot.espera_entre_intentos)
            if _esperar_o_cancelar(ejecucion, robot.espera_entre_intentos):
                return Ejecucion.Estado.CANCELADA, "Ejecución cancelada por un usuario", ""


def _intento(ejecucion, instancia, config, valores, conexion):
    vigilante = VigilanteSeguridad(
        instancia.carpetas_autorizadas(config),
        permitir_abrir=instancia.permitir_abrir_archivos(config),
        log=log,
    )
    with vigilante, ConectorSAP(conexion, log) as sesion:
        ctx = ContextoEjecucion(
            sesion=sesion,
            config=config,
            parametros=valores,
            log=log,
            cancelacion_solicitada=lambda: _cancelacion_solicitada(ejecucion),
        )
        try:
            return instancia.ejecutar(ctx)
        except (SinDatos, Cancelado):
            raise
        except Exception:
            _guardar_captura(ejecucion, sesion)
            raise


def _guardar_captura(ejecucion, sesion):
    relativa = f"capturas/ejecucion_{ejecucion.pk}_{timezone.now():%Y%m%d_%H%M%S}.png"
    if sesion.captura(settings.MEDIA_ROOT / relativa):
        _actualizar(ejecucion, captura=relativa)
        log.info("Captura de pantalla guardada")
    else:
        log.warning("No se pudo guardar la captura de pantalla")


def _cancelacion_solicitada(ejecucion):
    return Ejecucion.objects.filter(pk=ejecucion.pk, cancelacion_solicitada=True).exists()


def _esperar_o_cancelar(ejecucion, segundos):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if _cancelacion_solicitada(ejecucion):
            return True
        time.sleep(2)
    return False


def _actualizar(ejecucion, **campos):
    for campo, valor in campos.items():
        setattr(ejecucion, campo, valor)
    Ejecucion.objects.filter(pk=ejecucion.pk).update(**campos)
