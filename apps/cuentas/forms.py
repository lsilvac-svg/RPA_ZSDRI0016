from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from apps.core.forms import BootstrapFormMixin

from .models import Usuario
from .validadores import dominio_permitido


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label="Correo",
        widget=forms.EmailInput(attrs={
            "autofocus": True,
            "placeholder": f"usuario@{settings.DOMINIO_CORREO}",
        }),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "dominio": f"Solo pueden ingresar correos @{settings.DOMINIO_CORREO}.",
    }

    def clean(self):
        email = self.cleaned_data.get("username", "")
        if email and not dominio_permitido(email):
            raise forms.ValidationError(self.error_messages["dominio"], code="dominio")
        self.cleaned_data["username"] = email.lower()
        return super().clean()


class CambiarClaveForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class UsuarioForm(BootstrapFormMixin, forms.ModelForm):
    """Alta y edición de usuarios desde la interfaz (solo administradores)."""

    clave = forms.CharField(
        label="Contraseña",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Obligatoria al crear. Al editar, dejar vacía para no cambiarla.",
    )

    class Meta:
        model = Usuario
        fields = ["email", "first_name", "last_name", "rol", "is_active"]
        labels = {"is_active": "Activo"}

    def clean_email(self):
        return self.cleaned_data["email"].lower()

    def clean(self):
        datos = super().clean()
        if not self.instance.pk and not datos.get("clave"):
            self.add_error("clave", "Ingrese una contraseña para el nuevo usuario.")
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get("clave"):
            usuario.set_password(self.cleaned_data["clave"])
        if commit:
            usuario.save()
        return usuario
