from django.contrib import admin

from .models import (
    Ejecucion, EjecucionOrquestador, EstadoWorker, LogEjecucion, Orquestador, PasoOrquestador,
    Programacion, Robot,
)


@admin.register(Robot)
class RobotAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "credencial", "activo"]
    list_select_related = ["credencial__conexion"]
    readonly_fields = ["codigo"]


@admin.register(Programacion)
class ProgramacionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "robot", "orquestador", "frecuencia", "hora", "activa",
                    "proxima_ejecucion"]
    list_filter = ["activa", "frecuencia", "robot", "orquestador"]


class PasoOrquestadorInline(admin.TabularInline):
    model = PasoOrquestador
    extra = 0


@admin.register(Orquestador)
class OrquestadorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo", "actualizado"]
    inlines = [PasoOrquestadorInline]


@admin.register(EjecucionOrquestador)
class EjecucionOrquestadorAdmin(admin.ModelAdmin):
    list_display = ["id", "orquestador", "estado", "origen", "solicitada_por", "creada", "fin"]
    list_filter = ["estado", "orquestador"]


class LogEjecucionInline(admin.TabularInline):
    model = LogEjecucion
    extra = 0
    can_delete = False
    readonly_fields = ["fecha", "nivel", "mensaje"]


@admin.register(Ejecucion)
class EjecucionAdmin(admin.ModelAdmin):
    list_display = ["id", "robot", "estado", "origen", "cadena", "solicitada_por", "creada", "fin"]
    list_filter = ["estado", "origen", "robot"]
    inlines = [LogEjecucionInline]


admin.site.register(EstadoWorker)
