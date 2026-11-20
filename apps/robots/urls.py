from django.urls import path

from . import views

app_name = "robots"

urlpatterns = [
    path("robots/", views.RobotListView.as_view(), name="lista"),
    path("robots/<int:pk>/", views.RobotDetailView.as_view(), name="detalle"),
    path("robots/<int:pk>/ejecutar/", views.RobotEjecutarView.as_view(), name="ejecutar"),
    path("robots/<int:pk>/configurar/", views.RobotConfigurarView.as_view(), name="configurar"),

    path("ejecuciones/", views.EjecucionListView.as_view(), name="ejecuciones"),
    path("ejecuciones/<int:pk>/", views.EjecucionDetailView.as_view(), name="ejecucion"),
    path("ejecuciones/<int:pk>/cancelar/", views.EjecucionCancelarView.as_view(), name="cancelar"),
    path("ejecuciones/<int:pk>/reintentar/", views.EjecucionReintentarView.as_view(), name="reintentar"),
    path("ejecuciones/<int:pk>/captura/", views.EjecucionCapturaView.as_view(), name="captura"),

    path("monitor/", views.MonitorView.as_view(), name="monitor"),
    path("worker/", views.WorkerCambiarView.as_view(), name="worker_cambiar"),

    path("programaciones/", views.ProgramacionListView.as_view(), name="programaciones"),
    path("programaciones/nueva/", views.ProgramacionCrearView.as_view(), name="programacion_crear"),
    path("programaciones/<int:pk>/editar/", views.ProgramacionEditarView.as_view(), name="programacion_editar"),
    path("programaciones/<int:pk>/eliminar/", views.ProgramacionEliminarView.as_view(), name="programacion_eliminar"),
    path("programaciones/<int:pk>/alternar/", views.ProgramacionAlternarView.as_view(), name="programacion_alternar"),
    path("programaciones/orquestador/nueva/", views.ProgramacionOrquestadorCrearView.as_view(), name="programacion_orquestador_crear"),
    path("programaciones/<int:pk>/orquestador/", views.ProgramacionOrquestadorEditarView.as_view(), name="programacion_orquestador_editar"),
    path("parametros-robot/", views.ParametrosRobotView.as_view(), name="parametros_robot"),
    path("pasos-orquestador/", views.PasosOrquestadorView.as_view(), name="pasos_orquestador"),

    path("orquestadores/", views.OrquestadorListView.as_view(), name="orquestadores"),
    path("orquestadores/nuevo/", views.OrquestadorCrearView.as_view(), name="orquestador_crear"),
    path("orquestadores/<int:pk>/", views.OrquestadorDetailView.as_view(), name="orquestador"),
    path("orquestadores/<int:pk>/editar/", views.OrquestadorEditarView.as_view(), name="orquestador_editar"),
    path("orquestadores/<int:pk>/eliminar/", views.OrquestadorEliminarView.as_view(), name="orquestador_eliminar"),
    path("orquestadores/<int:pk>/ejecutar/", views.OrquestadorEjecutarView.as_view(), name="orquestador_ejecutar"),
    path("orquestadores/<int:pk>/pasos/nuevo/", views.PasoCrearView.as_view(), name="paso_crear"),
    path("pasos/<int:pk>/editar/", views.PasoEditarView.as_view(), name="paso_editar"),
    path("pasos/<int:pk>/eliminar/", views.PasoEliminarView.as_view(), name="paso_eliminar"),
    path("pasos/<int:pk>/mover/", views.PasoMoverView.as_view(), name="paso_mover"),
    path("cadenas/<int:pk>/", views.CadenaDetailView.as_view(), name="cadena"),
    path("cadenas/<int:pk>/cancelar/", views.CadenaCancelarView.as_view(), name="cadena_cancelar"),
]
