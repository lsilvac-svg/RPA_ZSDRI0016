from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import CuentaGoogle, validar_clave_json

TAMANO_MAXIMO = 64 * 1024


class CuentaGoogleForm(BootstrapFormMixin, forms.ModelForm):
    archivo_clave = forms.FileField(
        label="Clave JSON de la cuenta de servicio",
        required=False,
        help_text=(
            "Archivo .json descargado de Google Cloud (IAM → Cuentas de servicio → "
            "Claves). Se guarda cifrado. Al editar, dejar vacío para no cambiarla."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".json,application/json"}),
    )

    class Meta:
        model = CuentaGoogle
        fields = ["nombre", "archivo_clave", "activa"]

    def clean_archivo_clave(self):
        archivo = self.cleaned_data.get("archivo_clave")
        if not archivo:
            if not self.instance.clave_cifrada:
                raise forms.ValidationError("Suba la clave JSON de la cuenta de servicio.")
            return None
        if archivo.size > TAMANO_MAXIMO:
            raise forms.ValidationError("El archivo es demasiado grande para ser una clave JSON.")
        try:
            texto = archivo.read().decode("utf-8")
        except UnicodeDecodeError:
            raise forms.ValidationError("El archivo no es un JSON de texto.")
        validar_clave_json(texto)
        return texto

    def save(self, commit=True):
        cuenta = super().save(commit=False)
        if self.cleaned_data.get("archivo_clave"):
            cuenta.clave = self.cleaned_data["archivo_clave"]
        if commit:
            cuenta.save()
        return cuenta
