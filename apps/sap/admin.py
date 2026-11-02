from django.contrib import admin

from .forms import ConexionSAPForm
from .models import ConexionSAP


@admin.register(ConexionSAP)
class ConexionSAPAdmin(admin.ModelAdmin):
    form = ConexionSAPForm
    list_display = ["nombre", "conexion_logon", "usuario", "activa", "actualizada"]
    list_filter = ["activa"]
