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

    path("programaciones/", views.ProgramacionListView.as_view(), name="programaciones"),
    path("programaciones/nueva/", views.ProgramacionCrearView.as_view(), name="programacion_crear"),
    path("programaciones/<int:pk>/editar/", views.ProgramacionEditarView.as_view(), name="programacion_editar"),
    path("programaciones/<int:pk>/eliminar/", views.ProgramacionEliminarView.as_view(), name="programacion_eliminar"),
    path("programaciones/<int:pk>/alternar/", views.ProgramacionAlternarView.as_view(), name="programacion_alternar"),
]
