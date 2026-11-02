from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "rol", "is_active", "last_login"]
    list_filter = ["rol", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Datos personales", {"fields": ["first_name", "last_name"]}),
        ("Acceso", {"fields": ["rol", "is_active", "is_superuser"]}),
        ("Fechas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"fields": ["email", "rol", "password1", "password2"]}),
    ]
