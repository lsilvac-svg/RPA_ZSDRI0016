"""Proceso que toma ejecuciones de la cola y las corre de a una.

Debe correr en una sesión de Windows con escritorio, porque SAP GUI
necesita una interfaz gráfica. Se inicia al iniciar sesión en Windows y
queda siempre en marcha; desde el panel un administrador lo activa o lo
pausa (EstadoWorker.habilitado).
"""
import logging
import os
import socket
import threading
import time

from django.db import DatabaseError, close_old_connections, connection
from django.utils import timezone

from apps.sap.motor.windows import exigir_windows, win32api, win32event, winerror

from . import ejecutor, planificador
from .models import Ejecucion, EstadoWorker, sincronizar_robots

log = logging.getLogger("rpa.worker")

NOMBRE_MUTEX = "Local\\RPA_SAP_WORKER"
INTERVALO_LATIDO = 10


class WorkerYaEnEjecucion(Exception):
    pass


class Latido(threading.Thread):
    """Reporta que el worker sigue vivo, también durante ejecuciones largas."""

    def __init__(self):
        super().__init__(daemon=True)
        self._fin = threading.Event()

    def run(self):
        while not self._fin.wait(INTERVALO_LATIDO):
            try:
                EstadoWorker.objects.filter(pk=1).update(ultimo_latido=timezone.now())
            except DatabaseError:
                log.warning("No se pudo registrar el latido (base de datos no disponible)")
            finally:
                connection.close()

    def detener(self):
        self._fin.set()


class Worker:
    def __init__(self, intervalo=5):
        self.intervalo = intervalo
        self._mutex = None
        self._habilitado_anterior = None

    def iniciar(self, una_vez=False):
        exigir_windows()
        self._bloquear_instancia()
        sincronizar_robots()
        self._recuperar_interrumpidas()
        self._registrar_inicio()
        log.info("Worker iniciado en %s (PID %s)", socket.gethostname(), os.getpid())

        latido = Latido()
        latido.start()
        try:
            while True:
                if not self._ciclo() and una_vez:
                    break
        finally:
            latido.detener()
            EstadoWorker.objects.filter(pk=1).update(ultimo_latido=None, ejecucion=None)
            log.info("Worker detenido")

    def _ciclo(self):
        """Un ciclo de trabajo. Devuelve True si procesó una ejecución."""
        try:
            close_old_connections()
            EstadoWorker.objects.filter(pk=1).update(ultimo_latido=timezone.now())
            planificador.encolar_vencidas()

            if not self._habilitado():
                time.sleep(self.intervalo)
                return False

            ejecucion = self._siguiente()
            if ejecucion is None:
                time.sleep(self.intervalo)
                return False
            self._procesar(ejecucion)
            return True
        except DatabaseError:
            # p. ej. el contenedor de PostgreSQL se está reiniciando
            log.exception("Base de datos no disponible; se reintenta en 15 s")
            connection.close()
            time.sleep(15)
            return False

    def _habilitado(self):
        habilitado = EstadoWorker.objects.values_list("habilitado", flat=True).get(pk=1)
        if habilitado != self._habilitado_anterior:
            log.info(
                "Worker %s",
                "activo: procesa la cola" if habilitado else "pausado desde el panel",
            )
            self._habilitado_anterior = habilitado
        return habilitado

    def _bloquear_instancia(self):
        self._mutex = win32event.CreateMutex(None, False, NOMBRE_MUTEX)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            raise WorkerYaEnEjecucion("Ya hay un worker ejecutándose en este equipo")

    def _recuperar_interrumpidas(self):
        # Ejecuciones que quedaron "ejecutando" si el worker se cerró de golpe
        cantidad = Ejecucion.objects.filter(estado=Ejecucion.Estado.EJECUTANDO).update(
            estado=Ejecucion.Estado.FALLIDA,
            fin=timezone.now(),
            mensaje="Interrumpida: el worker se detuvo durante la ejecución",
        )
        if cantidad:
            log.warning("%s ejecuciones interrumpidas marcadas como fallidas", cantidad)

    def _registrar_inicio(self):
        EstadoWorker.obtener()
        EstadoWorker.objects.filter(pk=1).update(
            equipo=socket.gethostname(),
            pid=os.getpid(),
            iniciado=timezone.now(),
            ultimo_latido=timezone.now(),
        )

    def _siguiente(self):
        pendientes = Ejecucion.objects.filter(
            estado=Ejecucion.Estado.PENDIENTE
        ).select_related("robot", "robot__conexion").order_by("creada")

        for ejecucion in pendientes:
            if ejecucion.cancelacion_solicitada:
                Ejecucion.objects.filter(pk=ejecucion.pk).update(
                    estado=Ejecucion.Estado.CANCELADA, fin=timezone.now()
                )
                continue
            return ejecucion
        return None

    def _procesar(self, ejecucion):
        EstadoWorker.objects.filter(pk=1).update(ejecucion=ejecucion)
        log.info("Procesando ejecución #%s (%s)", ejecucion.pk, ejecucion.robot)
        try:
            ejecutor.ejecutar(ejecucion)
        finally:
            EstadoWorker.objects.filter(pk=1).update(ejecucion=None)
