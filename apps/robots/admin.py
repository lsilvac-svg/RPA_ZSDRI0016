from django.contrib import admin

from .models import Ejecucion, EstadoWorker, LogEjecucion, Programacion, Robot


@admin.register(Robot)
class RobotAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "conexion", "activo"]
    readonly_fields = ["codigo"]


@admin.register(Programacion)
class ProgramacionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "robot", "frecuencia", "hora", "activa", "proxima_ejecucion"]
    list_filter = ["activa", "frecuencia", "robot"]


class LogEjecucionInline(admin.TabularInline):
    model = LogEjecucion
    extra = 0
    can_delete = False
    readonly_fields = ["fecha", "nivel", "mensaje"]


@admin.register(Ejecucion)
class EjecucionAdmin(admin.ModelAdmin):
    list_display = ["id", "robot", "estado", "origen", "solicitada_por", "creada", "fin"]
    list_filter = ["estado", "origen", "robot"]
    inlines = [LogEjecucionInline]


admin.site.register(EstadoWorker)
