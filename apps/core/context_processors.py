from apps.robots.models import EstadoWorker


def estado_worker(request):
    """Estado del worker para el indicador del sidebar en todas las páginas."""
    if not request.user.is_authenticated:
        return {}
    return {"worker": EstadoWorker.obtener()}
