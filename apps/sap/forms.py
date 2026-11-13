from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import ConexionSAP, CredencialSAP


class ConexionSAPForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ConexionSAP
        fields = ["nombre", "conexion_logon", "ruta_saplogon", "tiempo_espera", "activa"]


class CredencialSAPForm(BootstrapFormMixin, forms.ModelForm):
    clave = forms.CharField(
        label="Contraseña SAP",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Se guarda cifrada. Al editar, dejar vacía para no cambiarla.",
    )

    class Meta:
        model = CredencialSAP
        fields = [
            "conexion", "usuario", "clave", "descripcion",
            "finalizar_otras_sesiones", "activa",
        ]

    def clean_usuario(self):
        return self.cleaned_data["usuario"].strip().upper()

    def clean(self):
        datos = super().clean()
        if not self.instance.clave_cifrada and not datos.get("clave"):
            self.add_error("clave", "Ingrese la contraseña SAP.")
        return datos

    def save(self, commit=True):
        credencial = super().save(commit=False)
        if self.cleaned_data.get("clave"):
            credencial.clave = self.cleaned_data["clave"]
        if commit:
            credencial.save()
        return credencial
