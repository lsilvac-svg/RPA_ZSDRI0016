from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("", views.UsuarioListView.as_view(), name="lista"),
    path("nuevo/", views.UsuarioCrearView.as_view(), name="crear"),
    path("<int:pk>/editar/", views.UsuarioEditarView.as_view(), name="editar"),
    path("cambiar-clave/", views.CambiarClaveView.as_view(), name="cambiar_clave"),
]
