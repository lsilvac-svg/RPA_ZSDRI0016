from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.sap.models import ConexionSAP

from . import parametros, registro


class Robot(models.Model):
    """Un RPA instalado y su configuración (editable desde la interfaz)."""

    codigo = models.CharField(max_length=40, unique=True, editable=False)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    conexion = models.ForeignKey(
        ConexionSAP, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name="conexión SAP",
    )
    configuracion = models.JSONField(default=dict, blank=True)
    reintentos = models.PositiveSmallIntegerField(
        default=3, help_text="Intentos máximos ante errores recuperables."
    )
    espera_entre_intentos = models.PositiveIntegerField(
        "espera entre intentos (s)", default=30
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def clase(self):
        return registro.obtener(self.codigo)

    @property
    def instalado(self):
        return self.codigo in registro.todos()

    def config_efectiva(self):
        return parametros.resolver(self.clase.parametros_config, self.configuracion)

    @property
    def ultima_ejecucion(self):
        return self.ejecuciones.first()


def sincronizar_robots():
    """Crea en la BD los robots registrados que aún no existen."""
    for codigo, clase in registro.todos().items():
        Robot.objects.get_or_create(
            codigo=codigo,
            defaults={"nombre": clase.nombre, "descripcion": clase.descripcion},
        )


class Programacion(models.Model):
    """Ejecución automática recurrente de un robot."""

    class Frecuencia(models.TextChoices):
        DIARIA = "DIARIA", "Diaria"
        SEMANAL = "SEMANAL", "Semanal"
        MENSUAL = "MENSUAL", "Mensual"

    DIAS_SEMANA = [
        ("0", "Lunes"), ("1", "Martes"), ("2", "Miércoles"), ("3", "Jueves"),
        ("4", "Viernes"), ("5", "Sábado"), ("6", "Domingo"),
    ]

    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="programaciones")
    nombre = models.CharField(max_length=120)
    frecuencia = models.CharField(max_length=10, choices=Frecuencia.choices)
    hora = models.TimeField()
    dias_semana = models.CharField(
        "días de la semana", max_length=20, blank=True,
        help_text="Solo para frecuencia semanal.",
    )
    dia_mes = models.PositiveSmallIntegerField(
        "día del mes", null=True, blank=True,
        help_text="Solo para frecuencia mensual. Si el mes es más corto, se usa el último día.",
    )
    activa = models.BooleanField(default=True)
    ultima_ejecucion = models.DateTimeField(null=True, blank=True, editable=False)
    proxima_ejecucion = models.DateTimeField(null=True, blank=True, editable=False)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "programación"
        verbose_name_plural = "programaciones"
        ordering = ["robot__nombre", "hora"]

    def __str__(self):
        return f"{self.nombre} ({self.robot})"

    @property
    def dias_semana_lista(self):
        return [int(d) for d in self.dias_semana.split(",") if d != ""]

    def descripcion_frecuencia(self):
        hora = self.hora.strftime("%H:%M")
        if self.frecuencia == self.Frecuencia.SEMANAL:
            nombres = dict(self.DIAS_SEMANA)
            dias = ", ".join(nombres[str(d)] for d in self.dias_semana_lista)
            return f"{dias} a las {hora}"
        if self.frecuencia == self.Frecuencia.MENSUAL:
            return f"Día {self.dia_mes} de cada mes a las {hora}"
        return f"Todos los días a las {hora}"

    def save(self, *args, **kwargs):
        from .planificador import calcular_proxima

        self.proxima_ejecucion = calcular_proxima(self, timezone.now()) if self.activa else None
        super().save(*args, **kwargs)


class Ejecucion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EJECUTANDO = "EJECUTANDO", "Ejecutando"
        EXITOSA = "EXITOSA", "Exitosa"
        SIN_DATOS = "SIN_DATOS", "Sin datos"
        FALLIDA = "FALLIDA", "Fallida"
        CANCELADA = "CANCELADA", "Cancelada"

    class Origen(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        PROGRAMADA = "PROGRAMADA", "Programada"

    ESTADOS_ACTIVOS = [Estado.PENDIENTE, Estado.EJECUTANDO]
    COLORES = {
        Estado.PENDIENTE: "secondary",
        Estado.EJECUTANDO: "primary",
        Estado.EXITOSA: "success",
        Estado.SIN_DATOS: "info",
        Estado.FALLIDA: "danger",
        Estado.CANCELADA: "warning",
    }

    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="ejecuciones")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.MANUAL)
    programacion = models.ForeignKey(
        Programacion, on_delete=models.SET_NULL, null=True, blank=True
    )
    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    parametros = models.JSONField(default=dict, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    inicio = models.DateTimeField(null=True, blank=True)
    fin = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    mensaje = models.TextField(blank=True)
    archivo = models.CharField("archivo generado", max_length=500, blank=True)
    captura = models.CharField(max_length=255, blank=True)
    cancelacion_solicitada = models.BooleanField(default=False)

    class Meta:
        verbose_name = "ejecución"
        verbose_name_plural = "ejecuciones"
        ordering = ["-creada"]
        indexes = [models.Index(fields=["estado", "creada"])]

    def __str__(self):
        return f"#{self.pk} {self.robot} ({self.get_estado_display()})"

    @property
    def color(self):
        return self.COLORES.get(self.estado, "secondary")

    @property
    def activa(self):
        return self.estado in self.ESTADOS_ACTIVOS

    @property
    def duracion(self):
        if not self.inicio:
            return None
        return (self.fin or timezone.now()) - self.inicio

    def puede_cancelar(self, usuario):
        return self.activa and not self.cancelacion_solicitada and (
            usuario.es_admin or self.solicitada_por_id == usuario.pk
        )

    @property
    def puede_reintentar(self):
        return self.estado in (self.Estado.FALLIDA, self.Estado.CANCELADA)


class LogEjecucion(models.Model):
    ejecucion = models.ForeignKey(Ejecucion, on_delete=models.CASCADE, related_name="logs")
    fecha = models.DateTimeField(auto_now_add=True)
    nivel = models.CharField(max_length=10)
    mensaje = models.TextField()

    class Meta:
        ordering = ["id"]

    COLORES = {"WARNING": "warning", "ERROR": "danger", "CRITICAL": "danger"}

    @property
    def color(self):
        return self.COLORES.get(self.nivel, "")


class EstadoWorker(models.Model):
    """Fila única con el latido del worker que ejecuta los robots."""

    LIMITE_LATIDO = timedelta(seconds=30)

    equipo = models.CharField(max_length=120, blank=True)
    pid = models.PositiveIntegerField(null=True, blank=True)
    iniciado = models.DateTimeField(null=True, blank=True)
    ultimo_latido = models.DateTimeField(null=True, blank=True)
    ejecucion = models.ForeignKey(Ejecucion, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "estado del worker"

    @classmethod
    def obtener(cls):
        estado, _ = cls.objects.get_or_create(pk=1)
        return estado

    @property
    def activo(self):
        return bool(
            self.ultimo_latido
            and timezone.now() - self.ultimo_latido < self.LIMITE_LATIDO
        )
