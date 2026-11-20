"""Ejecución en cadena de los robots de un orquestador.

Al iniciar se encola solo el primer paso. Cuando una ejecución de la cadena
termina, `avanzar()` encola el paso siguiente si fue EXITOSA o SIN_DATOS;
si falló o se canceló, la cadena se detiene. Los pasos heredan la posición
de la cadena en la cola, así el siguiente robot corre apenas termina el
anterior.

Para evitar encolamientos duplicados, `robot_ocupado()` indica si un robot
ya está en cola, ejecutándose o pendiente dentro de una cadena activa.
"""
import logging

from django.db import transaction
from django.utils import timezone

from .models import Ejecucion, EjecucionOrquestador

log = logging.getLogger("rpa.orquestacion")


ESTADOS_QUE_CONTINUAN = (Ejecucion.Estado.EXITOSA, Ejecucion.Estado.SIN_DATOS)


class OrquestadorNoDisponible(Exception):
    pass


def robot_ocupado(robot):
    """Motivo por el que no conviene encolar el robot ahora, o None si está libre."""
    activa = robot.ejecuciones.filter(estado__in=Ejecucion.ESTADOS_ACTIVOS).first()
    if activa:
        return f"el robot {robot} ya tiene la ejecución #{activa.pk} {activa.get_estado_display().lower()}"

    cadenas = EjecucionOrquestador.objects.filter(
        estado=EjecucionOrquestador.Estado.EJECUTANDO, orquestador__pasos__robot=robot,
    ).distinct().select_related("orquestador")
    for cadena in cadenas:
        ejecutados = set(cadena.pasos.values_list("paso_id", flat=True))
        if cadena.orquestador.pasos.filter(robot=robot).exclude(pk__in=ejecutados).exists():
            return (
                f"el robot {robot} tiene un paso pendiente en la cadena #{cadena.pk} "
                f"({cadena.orquestador})"
            )
    return None


def iniciar(orquestador, usuario=None, origen=Ejecucion.Origen.MANUAL, programacion=None):
    """Crea la corrida del orquestador y encola su primer paso."""
    if not orquestador.activo:
        raise OrquestadorNoDisponible("El orquestador está inactivo.")
    problemas = orquestador.problemas()
    if problemas:
        raise OrquestadorNoDisponible(" ".join(problemas))
    if orquestador.ejecuciones.filter(estado=EjecucionOrquestador.Estado.EJECUTANDO).exists():
        raise OrquestadorNoDisponible("El orquestador ya tiene una cadena en curso.")
    robots = {paso.robot_id: paso.robot for paso in orquestador.pasos.select_related("robot")}
    for robot in robots.values():
        motivo = robot_ocupado(robot)
        if motivo:
            raise OrquestadorNoDisponible(f"No se inicia la cadena: {motivo}.")

    with transaction.atomic():
        cadena = EjecucionOrquestador.objects.create(
            orquestador=orquestador, origen=origen, programacion=programacion,
            solicitada_por=usuario,
        )
        _encolar(cadena, orquestador.pasos.first())
    return cadena


def avanzar(ejecucion):
    """Llamar cuando una ejecución termina: encola el paso siguiente o cierra la cadena."""
    if not ejecucion.cadena_id:
        return
    with transaction.atomic():
        cadena = EjecucionOrquestador.objects.select_for_update().get(pk=ejecucion.cadena_id)
        if not cadena.activa:
            return

        if ejecucion.estado not in ESTADOS_QUE_CONTINUAN:
            estado = (
                EjecucionOrquestador.Estado.CANCELADA
                if ejecucion.estado == Ejecucion.Estado.CANCELADA
                else EjecucionOrquestador.Estado.DETENIDA
            )
            _cerrar(cadena, estado, (
                f"Detenida en el paso {_orden(ejecucion)} ({ejecucion.robot}): "
                f"{ejecucion.get_estado_display().lower()}. {ejecucion.mensaje}".strip()
            ))
            return

        if ejecucion.estado == Ejecucion.Estado.SIN_DATOS:
            log.info("Cadena #%s: paso %s sin datos; se continúa con el siguiente",
                     cadena.pk, _orden(ejecucion))

        siguiente = ejecucion.paso.siguiente if ejecucion.paso else None
        if siguiente is None:
            sin_datos = cadena.pasos.filter(estado=Ejecucion.Estado.SIN_DATOS).count()
            mensaje = "Todos los pasos terminaron."
            if sin_datos:
                mensaje += f" {sin_datos} paso(s) sin datos."
            _cerrar(cadena, EjecucionOrquestador.Estado.EXITOSA, mensaje)
            return
        _encolar(cadena, siguiente)


def cancelar(cadena, usuario):
    """Cancela la cadena: el paso pendiente se anula y el que corre se detiene."""
    with transaction.atomic():
        for ejecucion in cadena.pasos.filter(estado__in=Ejecucion.ESTADOS_ACTIVOS):
            if ejecucion.estado == Ejecucion.Estado.PENDIENTE:
                Ejecucion.objects.filter(pk=ejecucion.pk).update(
                    estado=Ejecucion.Estado.CANCELADA, fin=timezone.now(),
                    mensaje=f"Cancelada por {usuario}",
                )
            else:
                Ejecucion.objects.filter(pk=ejecucion.pk).update(cancelacion_solicitada=True)
        _cerrar(cadena, EjecucionOrquestador.Estado.CANCELADA, f"Cancelada por {usuario}")


def _encolar(cadena, paso):
    log.info("Cadena #%s: encolando paso %s (%s)", cadena.pk, paso.orden, paso.robot)
    return Ejecucion.objects.create(
        robot=paso.robot,
        origen=cadena.origen,
        programacion=cadena.programacion,
        solicitada_por=cadena.solicitada_por,
        parametros=paso.parametros,
        cadena=cadena,
        paso=paso,
    )


def _cerrar(cadena, estado, mensaje):
    EjecucionOrquestador.objects.filter(pk=cadena.pk).update(
        estado=estado, mensaje=mensaje, fin=timezone.now()
    )
    log.info("Cadena #%s: %s. %s", cadena.pk, estado, mensaje)


def _orden(ejecucion):
    return ejecucion.paso.orden if ejecucion.paso else "?"
