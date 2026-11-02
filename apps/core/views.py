from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import TemplateView

from apps.robots.models import Ejecucion, Programacion, Robot


class PanelView(TemplateView):
    """Panel principal: indicadores del día y últimas ejecuciones."""

    template_name = "core/panel.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        inicio_dia = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        hoy = Ejecucion.objects.filter(creada__gte=inicio_dia)
        contexto["indicadores"] = hoy.aggregate(
            total=Count("id"),
            exitosas=Count("id", filter=Q(estado=Ejecucion.Estado.EXITOSA)),
            fallidas=Count("id", filter=Q(estado=Ejecucion.Estado.FALLIDA)),
            en_curso=Count("id", filter=Q(estado__in=Ejecucion.ESTADOS_ACTIVOS)),
        )
        contexto["robots_activos"] = Robot.objects.filter(activo=True).count()
        contexto["proximas"] = (
            Programacion.objects.filter(activa=True, proxima_ejecucion__isnull=False)
            .select_related("robot")
            .order_by("proxima_ejecucion")[:5]
        )
        contexto["ultimas"] = Ejecucion.objects.select_related("robot")[:10]
        contexto["fallidas_semana"] = Ejecucion.objects.filter(
            estado=Ejecucion.Estado.FALLIDA,
            creada__gte=timezone.now() - timedelta(days=7),
        ).count()
        return contexto
