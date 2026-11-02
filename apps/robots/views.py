from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView,
)

from apps.cuentas.permisos import AdminRequeridoMixin

from . import parametros as params
from .forms import FiltroEjecucionesForm, ProgramacionForm, RobotForm
from .models import Ejecucion, EstadoWorker, Programacion, Robot, sincronizar_robots

PREFIJO_EJECUCION = "ej"
PREFIJO_CONFIG = "cfg"


# ==============================================
# ROBOTS
# ==============================================

class RobotListView(ListView):
    template_name = "robots/robot_lista.html"
    context_object_name = "robots"

    def get_queryset(self):
        sincronizar_robots()
        return Robot.objects.select_related("conexion")


class RobotDetailView(DetailView):
    model = Robot
    template_name = "robots/robot_detalle.html"
    context_object_name = "robot"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        robot = self.object
        if robot.instalado:
            contexto["form_ejecutar"] = params.construir_formulario(
                robot.clase.parametros_ejecucion, prefix=PREFIJO_EJECUCION
            )
            contexto["configuracion"] = [
                (p.etiqueta, valor)
                for p, valor in zip(
                    robot.clase.parametros_config, robot.config_efectiva().values()
                )
            ]
        contexto["ejecuciones"] = robot.ejecuciones.select_related("solicitada_por")[:10]
        contexto["programaciones"] = robot.programaciones.all()
        return contexto


class RobotEjecutarView(View):
    """Encola una ejecución manual (perfil Usuario y Administrador)."""

    def post(self, request, pk):
        robot = get_object_or_404(Robot, pk=pk)
        if not robot.instalado:
            messages.error(request, "El código de este robot no está instalado.")
            return redirect("robots:detalle", pk=pk)
        if not robot.activo:
            messages.error(request, "El robot está inactivo.")
            return redirect("robots:detalle", pk=pk)
        if robot.conexion is None:
            messages.error(request, "El robot no tiene una conexión SAP asignada.")
            return redirect("robots:detalle", pk=pk)

        definicion = robot.clase.parametros_ejecucion
        form = params.construir_formulario(definicion, data=request.POST, prefix=PREFIJO_EJECUCION)
        if not form.is_valid():
            messages.error(request, "Revise los parámetros de la ejecución.")
            return redirect("robots:detalle", pk=pk)

        ejecucion = Ejecucion.objects.create(
            robot=robot,
            solicitada_por=request.user,
            parametros=params.serializar(definicion, form.cleaned_data),
        )
        messages.success(request, f"Ejecución #{ejecucion.pk} encolada.")
        if not EstadoWorker.obtener().activo:
            messages.warning(
                request,
                "El worker no está activo: la ejecución esperará hasta que se inicie.",
            )
        return redirect("robots:ejecucion", pk=ejecucion.pk)


class RobotConfigurarView(AdminRequeridoMixin, View):
    template_name = "robots/robot_configurar.html"

    def _formularios(self, robot, data=None):
        general = RobotForm(data=data, instance=robot, prefix="gen")
        propios = params.construir_formulario(
            robot.clase.parametros_config,
            data=data,
            valores=robot.configuracion,
            prefix=PREFIJO_CONFIG,
        )
        return general, propios

    def get(self, request, pk):
        robot = get_object_or_404(Robot, pk=pk)
        general, propios = self._formularios(robot)
        return render(request, self.template_name, {"robot": robot, "general": general, "propios": propios})

    def post(self, request, pk):
        robot = get_object_or_404(Robot, pk=pk)
        general, propios = self._formularios(robot, data=request.POST)
        if general.is_valid() and propios.is_valid():
            robot = general.save(commit=False)
            robot.configuracion = params.serializar(
                robot.clase.parametros_config, propios.cleaned_data
            )
            robot.save()
            messages.success(request, "Configuración guardada.")
            return redirect("robots:detalle", pk=pk)
        return render(request, self.template_name, {"robot": robot, "general": general, "propios": propios})


# ==============================================
# EJECUCIONES
# ==============================================

class EjecucionListView(ListView):
    template_name = "robots/ejecucion_lista.html"
    context_object_name = "ejecuciones"
    paginate_by = 25

    def get_queryset(self):
        self.filtro = FiltroEjecucionesForm(self.request.GET or None)
        consulta = Ejecucion.objects.select_related("robot", "solicitada_por")
        return self.filtro.filtrar(consulta)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["filtro"] = self.filtro
        consulta = self.request.GET.copy()
        consulta.pop("page", None)
        contexto["consulta"] = consulta.urlencode()
        return contexto


class EjecucionDetailView(DetailView):
    model = Ejecucion
    context_object_name = "ejecucion"

    def get_queryset(self):
        return Ejecucion.objects.select_related("robot", "solicitada_por", "programacion")

    def get_template_names(self):
        # Con HTMX se refresca solo el bloque de estado y logs
        if self.request.headers.get("HX-Request"):
            return ["robots/_ejecucion_estado.html"]
        return ["robots/ejecucion_detalle.html"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        ejecucion = self.object
        contexto["logs"] = ejecucion.logs.all()
        contexto["puede_cancelar"] = ejecucion.puede_cancelar(self.request.user)
        if ejecucion.robot.instalado:
            definicion = ejecucion.robot.clase.parametros_ejecucion
            contexto["parametros"] = [
                (p.etiqueta, ejecucion.parametros.get(p.nombre) or "Por defecto")
                for p in definicion
            ]
        return contexto


class EjecucionCancelarView(View):
    def post(self, request, pk):
        ejecucion = get_object_or_404(Ejecucion, pk=pk)
        if not ejecucion.puede_cancelar(request.user):
            raise PermissionDenied("No puede cancelar esta ejecución.")

        if ejecucion.estado == Ejecucion.Estado.PENDIENTE:
            Ejecucion.objects.filter(pk=pk, estado=Ejecucion.Estado.PENDIENTE).update(
                estado=Ejecucion.Estado.CANCELADA,
                fin=timezone.now(),
                mensaje=f"Cancelada por {request.user}",
            )
            messages.success(request, "Ejecución cancelada.")
        else:
            Ejecucion.objects.filter(pk=pk).update(cancelacion_solicitada=True)
            messages.info(request, "Cancelación solicitada: el robot se detendrá en el próximo paso.")
        return redirect("robots:ejecucion", pk=pk)


class EjecucionReintentarView(View):
    def post(self, request, pk):
        original = get_object_or_404(Ejecucion, pk=pk)
        if not original.puede_reintentar:
            messages.error(request, "Solo se pueden reintentar ejecuciones fallidas o canceladas.")
            return redirect("robots:ejecucion", pk=pk)

        nueva = Ejecucion.objects.create(
            robot=original.robot,
            solicitada_por=request.user,
            parametros=original.parametros,
        )
        messages.success(request, f"Ejecución #{nueva.pk} encolada.")
        return redirect("robots:ejecucion", pk=nueva.pk)


class EjecucionCapturaView(View):
    def get(self, request, pk):
        ejecucion = get_object_or_404(Ejecucion, pk=pk)
        ruta = (settings.MEDIA_ROOT / ejecucion.captura).resolve()
        if not ejecucion.captura or not ruta.is_file() or settings.MEDIA_ROOT.resolve() not in ruta.parents:
            raise Http404("Captura no disponible")
        return FileResponse(open(ruta, "rb"), content_type="image/png")


# ==============================================
# MONITOR
# ==============================================

class MonitorView(TemplateView):
    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["robots/_monitor.html"]
        return ["robots/monitor.html"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        en_curso = (
            Ejecucion.objects.filter(estado=Ejecucion.Estado.EJECUTANDO)
            .select_related("robot", "solicitada_por")
            .first()
        )
        contexto["en_curso"] = en_curso
        contexto["logs"] = list(en_curso.logs.order_by("-id")[:15])[::-1] if en_curso else []
        contexto["cola"] = (
            Ejecucion.objects.filter(estado=Ejecucion.Estado.PENDIENTE)
            .select_related("robot", "solicitada_por")
            .order_by("creada")
        )
        contexto["recientes"] = (
            Ejecucion.objects.exclude(estado__in=Ejecucion.ESTADOS_ACTIVOS)
            .select_related("robot")[:8]
        )
        contexto["estado_worker"] = EstadoWorker.obtener()
        return contexto


# ==============================================
# PROGRAMACIONES (solo administradores)
# ==============================================

LISTA_PROGRAMACIONES = reverse_lazy("robots:programaciones")


class ProgramacionListView(AdminRequeridoMixin, ListView):
    template_name = "robots/programacion_lista.html"
    context_object_name = "programaciones"

    def get_queryset(self):
        return Programacion.objects.select_related("robot")


class ProgramacionCrearView(AdminRequeridoMixin, CreateView):
    model = Programacion
    form_class = ProgramacionForm
    template_name = "core/formulario.html"
    success_url = LISTA_PROGRAMACIONES
    extra_context = {"titulo": "Nueva programación", "volver": LISTA_PROGRAMACIONES}

    def get_initial(self):
        return {"robot": self.request.GET.get("robot")}

    def form_valid(self, form):
        form.instance.creada_por = self.request.user
        messages.success(self.request, "Programación creada.")
        return super().form_valid(form)


class ProgramacionEditarView(AdminRequeridoMixin, UpdateView):
    model = Programacion
    form_class = ProgramacionForm
    template_name = "core/formulario.html"
    success_url = LISTA_PROGRAMACIONES
    extra_context = {"titulo": "Editar programación", "volver": LISTA_PROGRAMACIONES}

    def form_valid(self, form):
        messages.success(self.request, "Programación actualizada.")
        return super().form_valid(form)


class ProgramacionEliminarView(AdminRequeridoMixin, DeleteView):
    model = Programacion
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA_PROGRAMACIONES
    extra_context = {"volver": LISTA_PROGRAMACIONES}

    def form_valid(self, form):
        messages.success(self.request, "Programación eliminada.")
        return super().form_valid(form)


class ProgramacionAlternarView(AdminRequeridoMixin, View):
    def post(self, request, pk):
        programacion = get_object_or_404(Programacion, pk=pk)
        programacion.activa = not programacion.activa
        programacion.save()
        estado = "activada" if programacion.activa else "pausada"
        messages.success(request, f"Programación {estado}.")
        return redirect(request.POST.get("volver") or reverse("robots:programaciones"))
