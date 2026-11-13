from django.contrib import admin

from .forms import ConexionSAPForm, CredencialSAPForm
from .models import ConexionSAP, CredencialSAP


@admin.register(ConexionSAP)
class ConexionSAPAdmin(admin.ModelAdmin):
    form = ConexionSAPForm
    list_display = ["nombre", "conexion_logon", "activa", "actualizada"]
    list_filter = ["activa"]


@admin.register(CredencialSAP)
class CredencialSAPAdmin(admin.ModelAdmin):
    form = CredencialSAPForm
    list_display = ["usuario", "conexion", "descripcion", "activa", "actualizada"]
    list_filter = ["activa", "conexion"]
    list_select_related = ["conexion"]
