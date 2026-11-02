"""Proceso que toma ejecuciones de la cola y las corre de a una.

Debe correr en una sesión de Windows con escritorio, porque SAP GUI
necesita una interfaz gráfica.
"""
import logging
import os
import socket
import time

from django.db import close_old_connections
from django.utils import timezone

from apps.sap.motor.windows import exigir_windows, win32api, win32event, winerror

from . import ejecutor, planificador
from .models import Ejecucion, EstadoWorker, sincronizar_robots

log = logging.getLogger("rpa.worker")

NOMBRE_MUTEX = "Local\\RPA_SAP_WORKER"


class WorkerYaEnEjecucion(Exception):
    pass


class Worker:
    def __init__(self, intervalo=5):
        self.intervalo = intervalo
        self._mutex = None

    def iniciar(self, una_vez=False):
        exigir_windows()
        self._bloquear_instancia()
        sincronizar_robots()
        self._recuperar_interrumpidas()
        self._latido(iniciando=True)
        log.info("Worker iniciado en %s (PID %s)", socket.gethostname(), os.getpid())

        try:
            while True:
                close_old_connections()
                self._latido()
                planificador.encolar_vencidas()
                ejecucion = self._siguiente()
                if ejecucion is not None:
                    self._procesar(ejecucion)
                elif una_vez:
                    break
                else:
                    time.sleep(self.intervalo)
        finally:
            EstadoWorker.objects.filter(pk=1).update(ultimo_latido=None, ejecucion=None)
            log.info("Worker detenido")

    def _bloquear_instancia(self):
        self._mutex = win32event.CreateMutex(None, False, NOMBRE_MUTEX)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            raise WorkerYaEnEjecucion("Ya hay un worker ejecutándose en este equipo")

    def _recuperar_interrumpidas(self):
        # Ejecuciones que quedaron "ejecutando" si el worker se cerró de golpe
        interrumpidas = Ejecucion.objects.filter(estado=Ejecucion.Estado.EJECUTANDO)
        cantidad = interrumpidas.update(
            estado=Ejecucion.Estado.FALLIDA,
            fin=timezone.now(),
            mensaje="Interrumpida: el worker se detuvo durante la ejecución",
        )
        if cantidad:
            log.warning("%s ejecuciones interrumpidas marcadas como fallidas", cantidad)

    def _latido(self, iniciando=False):
        campos = {"ultimo_latido": timezone.now()}
        if iniciando:
            campos.update(
                equipo=socket.gethostname(), pid=os.getpid(), iniciado=timezone.now()
            )
        EstadoWorker.obtener()
        EstadoWorker.objects.filter(pk=1).update(**campos)

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
