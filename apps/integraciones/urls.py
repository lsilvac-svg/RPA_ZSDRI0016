from django.urls import path

from . import views

app_name = "integraciones"

urlpatterns = [
    path("google/", views.CuentaListView.as_view(), name="lista"),
    path("google/nueva/", views.CuentaCrearView.as_view(), name="crear"),
    path("google/<int:pk>/editar/", views.CuentaEditarView.as_view(), name="editar"),
    path("google/<int:pk>/eliminar/", views.CuentaEliminarView.as_view(), name="eliminar"),
]
