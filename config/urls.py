from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.cuentas.views import LoginView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("usuarios/", include("apps.cuentas.urls")),
    path("sap/", include("apps.sap.urls")),
    path("", include("apps.robots.urls")),
    path("", include("apps.core.urls")),
]

admin.site.site_header = "RPAs SAP – Administración"
admin.site.site_title = "RPAs SAP"
