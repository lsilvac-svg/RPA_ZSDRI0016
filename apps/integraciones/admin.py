from django.contrib import admin

from .forms import CuentaGoogleForm
from .models import CuentaGoogle


@admin.register(CuentaGoogle)
class CuentaGoogleAdmin(admin.ModelAdmin):
    form = CuentaGoogleForm
    list_display = ["nombre", "correo", "activa", "actualizada"]
    readonly_fields = ["correo"]
