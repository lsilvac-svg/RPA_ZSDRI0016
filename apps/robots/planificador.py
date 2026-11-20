"""Cálculo de próximas ejecuciones y encolado de programaciones vencidas."""
import calendar
import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

log = logging.getLogger("rpa.planificador")

DIAS_BUSQUEDA = 400


def calcular_proxima(programacion, despues):
    """Primera fecha/hora programada estrictamente posterior a `despues`."""
    from .models import Programacion

    zona = timezone.get_current_timezone()
    desde = timezone.localtime(despues, zona)

    for desplazamiento in range(DIAS_BUSQUEDA):
        dia = desde.date() + timedelta(days=desplazamiento)
        if not _corresponde(programacion, dia, Programacion.Frecuencia):
            continue
        candidata = timezone.make_aware(datetime.combine(dia, programacion.hora), zona)
        if candidata > desde:
            return candidata
    return None


def _corresponde(programacion, dia, frecuencia):
    if programacion.frecuencia == frecuencia.SEMANAL:
        return dia.weekday() in programacion.dias_semana_lista
    if programacion.frecuencia == frecuencia.MENSUAL:
        ultimo = calendar.monthrange(dia.year, dia.month)[1]
        return dia.day == min(programacion.dia_mes or 1, ultimo)
    return True


def encolar_vencidas(ahora=None):
    """Crea ejecuciones para las programaciones cuya hora ya llegó."""
    from .models import Programacion

    ahora = ahora or timezone.now()
    vencidas = Programacion.objects.filter(
        Q(robot__activo=True) | Q(orquestador__activo=True),
        activa=True, proxima_ejecucion__lte=ahora,
    ).select_related("robot", "orquestador")

    creadas = 0
    for programacion in vencidas:
        with transaction.atomic():
            if programacion.orquestador_id:
                creadas += _lanzar_orquestador(programacion)
            else:
                creadas += _encolar_robot(programacion)
            programacion.ultima_ejecucion = ahora
            programacion.save()  # recalcula la próxima ejecución
    return creadas


def _encolar_robot(programacion):
    from .models import Ejecucion
    from .orquestacion import robot_ocupado

    motivo = robot_ocupado(programacion.robot)
    if motivo:
        log.warning("Programación '%s' omitida: %s", programacion, motivo)
        return 0
    Ejecucion.objects.create(
        robot=programacion.robot,
        origen=Ejecucion.Origen.PROGRAMADA,
        programacion=programacion,
        parametros=programacion.parametros or {},
    )
    return 1


def _lanzar_orquestador(programacion):
    from . import orquestacion
    from .models import Ejecucion

    try:
        orquestacion.iniciar(
            programacion.orquestador, origen=Ejecucion.Origen.PROGRAMADA,
            programacion=programacion,
        )
    except orquestacion.OrquestadorNoDisponible as motivo:
        log.warning("Programación '%s' omitida: %s", programacion, motivo)
        return 0
    return 1
