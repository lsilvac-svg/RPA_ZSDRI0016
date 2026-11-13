import json

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.cifrado import cifrar, descifrar

CAMPOS_REQUERIDOS = ("type", "client_email", "private_key", "token_uri")


def validar_clave_json(texto):
    """Devuelve el dict de la clave de cuenta de servicio o lanza ValidationError."""
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        raise ValidationError("El archivo no es un JSON válido.")
    if not isinstance(datos, dict) or datos.get("type") != "service_account":
        raise ValidationError(
            "No es la clave de una cuenta de servicio (falta \"type\": \"service_account\")."
        )
    faltan = [c for c in CAMPOS_REQUERIDOS if not datos.get(c)]
    if faltan:
        raise ValidationError(f"A la clave le faltan los campos: {', '.join(faltan)}.")
    return datos


class CuentaGoogle(models.Model):
    """Cuenta de servicio de Google con la que los robots usan Drive y Sheets.

    Los archivos y carpetas de destino deben compartirse con su correo.
    """

    nombre = models.CharField(max_length=80, unique=True)
    correo = models.EmailField(
        "correo de la cuenta de servicio", editable=False,
        help_text="Compartir con este correo las carpetas y hojas de destino.",
    )
    clave_cifrada = models.TextField(editable=False)
    activa = models.BooleanField(default=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cuenta de Google"
        verbose_name_plural = "cuentas de Google"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.correo})"

    @property
    def clave(self):
        """Contenido JSON de la clave (descifrado)."""
        return descifrar(self.clave_cifrada) if self.clave_cifrada else ""

    @clave.setter
    def clave(self, texto):
        datos = validar_clave_json(texto)
        self.correo = datos["client_email"]
        self.clave_cifrada = cifrar(texto)

    def info_clave(self):
        return json.loads(self.clave)

    @classmethod
    def elegir(cls, nombre=""):
        """La cuenta indicada por nombre, o la única activa si no se indica."""
        activas = cls.objects.filter(activa=True)
        if nombre:
            cuenta = activas.filter(nombre=nombre).first()
            if cuenta is None:
                raise LookupError(f"No hay una cuenta de Google activa llamada '{nombre}'")
            return cuenta
        cuentas = list(activas[:2])
        if len(cuentas) != 1:
            raise LookupError(
                "Indique la cuenta de Google en la configuración del robot "
                f"(hay {activas.count()} cuentas activas)"
            )
        return cuentas[0]
