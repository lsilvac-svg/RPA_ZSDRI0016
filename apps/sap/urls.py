from django.urls import path

from . import views

app_name = "sap"

urlpatterns = [
    path("conexiones/", views.ConexionListView.as_view(), name="lista"),
    path("conexiones/nueva/", views.ConexionCrearView.as_view(), name="crear"),
    path("conexiones/<int:pk>/editar/", views.ConexionEditarView.as_view(), name="editar"),
    path("conexiones/<int:pk>/eliminar/", views.ConexionEliminarView.as_view(), name="eliminar"),
]
