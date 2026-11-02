from django.db import models

from apps.core.cifrado import cifrar, descifrar

from .motor import ParametrosConexion

RUTA_SAPLOGON_DEFECTO = r"C:\Program Files\SAP\FrontEnd\SAPgui\saplogon.exe"


class ConexionSAP(models.Model):
    """Sistema SAP y credenciales con las que se conectan los robots."""

    nombre = models.CharField(max_length=80, unique=True)
    conexion_logon = models.CharField(
        "conexión en SAP Logon",
        max_length=120,
        help_text="Texto de la columna 'Nombre' en SAP Logon, p. ej. PRD_HANA.",
    )
    usuario = models.CharField(max_length=40)
    clave_cifrada = models.TextField(editable=False)
    ruta_saplogon = models.CharField(
        "ruta de saplogon.exe", max_length=255, default=RUTA_SAPLOGON_DEFECTO
    )
    finalizar_otras_sesiones = models.BooleanField(
        default=True,
        help_text=(
            "Si el usuario tiene sesión abierta en otro equipo: finalizarla y "
            "continuar. Si está desmarcado, el robot se detiene."
        ),
    )
    tiempo_espera = models.PositiveIntegerField(
        "tiempo de espera (s)", default=30,
        help_text="Segundos máximos de espera por pantalla o ventana.",
    )
    activa = models.BooleanField(default=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "conexión SAP"
        verbose_name_plural = "conexiones SAP"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.usuario})"

    @property
    def clave(self):
        return descifrar(self.clave_cifrada) if self.clave_cifrada else ""

    @clave.setter
    def clave(self, valor):
        self.clave_cifrada = cifrar(valor)

    def parametros(self):
        """Parámetros para el motor SAP (con la contraseña descifrada)."""
        return ParametrosConexion(
            conexion_logon=self.conexion_logon,
            usuario=self.usuario,
            clave=self.clave,
            ruta_saplogon=self.ruta_saplogon,
            finalizar_otras_sesiones=self.finalizar_otras_sesiones,
            tiempo_espera=self.tiempo_espera,
        )
