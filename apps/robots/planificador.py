"""Cálculo de próximas ejecuciones y encolado de programaciones vencidas."""
import calendar
import logging
from datetime import datetime, timedelta

from django.db import transaction
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
    from .models import Ejecucion, Programacion

    ahora = ahora or timezone.now()
    vencidas = Programacion.objects.filter(
        activa=True, proxima_ejecucion__lte=ahora, robot__activo=True
    ).select_related("robot")

    creadas = 0
    for programacion in vencidas:
        with transaction.atomic():
            ya_en_cola = Ejecucion.objects.filter(
                robot=programacion.robot, estado__in=Ejecucion.ESTADOS_ACTIVOS
            ).exists()
            if ya_en_cola:
                log.warning(
                    "Programación '%s' omitida: el robot ya tiene una ejecución en curso",
                    programacion,
                )
            else:
                Ejecucion.objects.create(
                    robot=programacion.robot,
                    origen=Ejecucion.Origen.PROGRAMADA,
                    programacion=programacion,
                )
                creadas += 1

            programacion.ultima_ejecucion = ahora
            programacion.save()  # recalcula la próxima ejecución
    return creadas
