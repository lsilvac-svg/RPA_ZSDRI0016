from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import ConexionSAP


class ConexionSAPForm(BootstrapFormMixin, forms.ModelForm):
    clave = forms.CharField(
        label="Contraseña SAP",
        required=False,
        strip=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Se guarda cifrada. Al editar, dejar vacía para no cambiarla.",
    )

    class Meta:
        model = ConexionSAP
        fields = [
            "nombre", "conexion_logon", "usuario", "clave", "ruta_saplogon",
            "finalizar_otras_sesiones", "tiempo_espera", "activa",
        ]

    def clean_usuario(self):
        return self.cleaned_data["usuario"].strip().upper()

    def clean(self):
        datos = super().clean()
        if not self.instance.clave_cifrada and not datos.get("clave"):
            self.add_error("clave", "Ingrese la contraseña SAP.")
        return datos

    def save(self, commit=True):
        conexion = super().save(commit=False)
        if self.cleaned_data.get("clave"):
            conexion.clave = self.cleaned_data["clave"]
        if commit:
            conexion.save()
        return conexion
