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

from . import orquestacion
from . import parametros as params
from .forms import (
    FiltroEjecucionesForm, OrquestadorForm, PasoForm, ProgramacionForm,
    ProgramacionOrquestadorForm, RobotForm,
)
from .models import (
    EjecucionOrquestador, Ejecucion, EstadoWorker, Orquestador, PasoOrquestador,
    Programacion, Robot, sincronizar_robots,
)

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
        return Robot.objects.select_related("credencial__conexion")


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
        if robot.requiere_sap and robot.credencial is None:
            messages.error(request, "El robot no tiene un login SAP asignado.")
            return redirect("robots:detalle", pk=pk)
        motivo = orquestacion.robot_ocupado(robot)
        if motivo:
            messages.error(request, f"No se encoló: {motivo}.")
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
        worker = EstadoWorker.obtener()
        if not worker.activo:
            messages.warning(
                request,
                f"El worker está {worker.get_estado_display().lower()}: la ejecución "
                "quedará en cola hasta que se active (ver Monitor).",
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
        return Ejecucion.objects.select_related(
            "robot", "solicitada_por", "programacion", "cadena__orquestador", "paso"
        )

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
            contexto["parametros"] = params.legibles(
                ejecucion.robot.clase.parametros_ejecucion, ejecucion.parametros
            )
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
            ejecucion.refresh_from_db()
            orquestacion.avanzar(ejecucion)  # detiene su cadena, si tiene
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
        motivo = orquestacion.robot_ocupado(original.robot)
        if motivo:
            messages.error(request, f"No se encoló: {motivo}.")
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


class WorkerCambiarView(AdminRequeridoMixin, View):
    """Activa o pausa el worker. Al pausar, la ejecución en curso termina
    normalmente y las nuevas quedan en cola."""

    def post(self, request):
        habilitar = request.POST.get("accion") == "activar"
        worker = EstadoWorker.obtener()
        worker.cambiar(habilitar, request.user)

        if habilitar and not worker.en_linea:
            messages.warning(
                request,
                "Worker activado, pero su proceso no está corriendo en el equipo "
                "Windows. Se iniciará solo al iniciar sesión en Windows "
                "(o ejecutar scripts\\iniciar_worker.bat).",
            )
        elif habilitar:
            messages.success(request, "Worker activado: procesará la cola.")
        else:
            messages.info(
                request,
                "Worker pausado: no tomará ejecuciones nuevas. Si hay una en curso, terminará.",
            )
        return redirect(request.POST.get("volver") or reverse("robots:monitor"))


# ==============================================
# PROGRAMACIONES (solo administradores)
# ==============================================

LISTA_PROGRAMACIONES = reverse_lazy("robots:programaciones")


def formulario_parametros_robot(robot, data=None, valores=None):
    """Formulario de los parámetros de ejecución de un robot (o None si no tiene)."""
    if robot is None or not robot.instalado or not robot.clase.parametros_ejecucion:
        return None
    return params.construir_formulario(
        robot.clase.parametros_ejecucion, data=data, valores=valores, prefix=PREFIJO_EJECUCION
    )


def robot_elegido(valor):
    if not valor:
        return None
    return Robot.objects.filter(pk=valor).first() if str(valor).isdigit() else None


class ParametrosRobotView(AdminRequeridoMixin, View):
    """Fragmento HTMX: parámetros de ejecución del robot elegido en un formulario."""

    def get(self, request):
        robot = robot_elegido(request.GET.get("robot"))
        return render(request, "robots/_parametros_robot.html", {
            "form_parametros": formulario_parametros_robot(robot), "robot": robot,
        })


class FormularioConParametrosMixin:
    """Formulario principal (con campo robot) + parámetros de ejecución del robot.

    Las subclases definen form_class, titulo, volver y guardar().
    """

    template_name = "robots/formulario_con_parametros.html"
    titulo = ""
    instancia = None

    def get_volver(self):
        return self.volver

    def _formularios(self, data=None, inicial=None):
        form = self.form_class(
            data=data, instance=self.instancia, initial=inicial,
            url_parametros=reverse("robots:parametros_robot"),
        )
        if data is not None:
            robot = robot_elegido(data.get("robot"))
        else:
            robot = robot_elegido((inicial or {}).get("robot")) or getattr(
                self.instancia, "robot", None
            )
        mismo_robot = self.instancia is not None and getattr(self.instancia, "robot_id", None) == (
            robot.pk if robot else None
        )
        valores = self.instancia.parametros if mismo_robot else None
        return form, formulario_parametros_robot(robot, data=data, valores=valores), robot

    def _render(self, form, form_parametros, robot):
        return render(self.request, self.template_name, {
            "titulo": self.titulo, "volver": self.get_volver(), "form": form,
            "form_parametros": form_parametros, "robot": robot,
        })

    def get(self, request, *args, **kwargs):
        return self._render(*self._formularios(inicial=self.get_initial()))

    def post(self, request, *args, **kwargs):
        form, form_parametros, robot = self._formularios(data=request.POST)
        if form.is_valid() and (form_parametros is None or form_parametros.is_valid()):
            valores = {}
            if form_parametros is not None:
                valores = params.serializar(robot.clase.parametros_ejecucion,
                                            form_parametros.cleaned_data)
            form.instance.parametros = valores
            return self.guardar(form)
        return self._render(form, form_parametros, robot)

    def get_initial(self):
        return {}


class ProgramacionListView(AdminRequeridoMixin, ListView):
    template_name = "robots/programacion_lista.html"
    context_object_name = "programaciones"

    def get_queryset(self):
        return Programacion.objects.select_related("robot", "orquestador").prefetch_related(
            "orquestador__pasos__robot"
        )


class ProgramacionCrearView(AdminRequeridoMixin, FormularioConParametrosMixin, View):
    form_class = ProgramacionForm
    titulo = "Nueva programación"
    volver = LISTA_PROGRAMACIONES

    titulo = "Programar robot"

    def get_initial(self):
        return {"robot": self.request.GET.get("robot")}

    def guardar(self, form):
        form.instance.creada_por = self.request.user
        form.save()
        messages.success(self.request, "Programación creada.")
        return redirect(LISTA_PROGRAMACIONES)


class ProgramacionEditarView(AdminRequeridoMixin, FormularioConParametrosMixin, View):
    form_class = ProgramacionForm
    titulo = "Editar programación de robot"
    volver = LISTA_PROGRAMACIONES

    def dispatch(self, request, *args, pk=None, **kwargs):
        self.instancia = get_object_or_404(Programacion, pk=pk)
        if self.instancia.orquestador_id:
            return redirect("robots:programacion_orquestador_editar", pk=pk)
        return super().dispatch(request, *args, **kwargs)

    def guardar(self, form):
        form.save()
        messages.success(self.request, "Programación actualizada.")
        return redirect(LISTA_PROGRAMACIONES)


class PasosOrquestadorView(AdminRequeridoMixin, View):
    """Fragmento HTMX: robots que ejecutará el orquestador elegido, en orden."""

    def get(self, request):
        valor = request.GET.get("orquestador", "")
        orquestador = Orquestador.objects.filter(pk=valor).first() if valor.isdigit() else None
        return render(request, "robots/_pasos_orquestador.html", {"orquestador": orquestador})


class ProgramacionOrquestadorMixin(AdminRequeridoMixin):
    model = Programacion
    form_class = ProgramacionOrquestadorForm
    template_name = "robots/programacion_orquestador.html"
    success_url = LISTA_PROGRAMACIONES

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "url_pasos": reverse("robots:pasos_orquestador")}

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        form = contexto["form"]
        valor = form["orquestador"].value()
        contexto["orquestador"] = (
            Orquestador.objects.filter(pk=valor).first() if str(valor or "").isdigit() else None
        )
        contexto["volver"] = LISTA_PROGRAMACIONES
        return contexto


class ProgramacionOrquestadorCrearView(ProgramacionOrquestadorMixin, CreateView):
    extra_context = {"titulo": "Programar orquestador"}

    def get_initial(self):
        return {"orquestador": self.request.GET.get("orquestador")}

    def form_valid(self, form):
        form.instance.creada_por = self.request.user
        messages.success(self.request, "Programación del orquestador creada.")
        return super().form_valid(form)


class ProgramacionOrquestadorEditarView(ProgramacionOrquestadorMixin, UpdateView):
    extra_context = {"titulo": "Editar programación de orquestador"}

    def get_queryset(self):
        return Programacion.objects.filter(orquestador__isnull=False)

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


# ==============================================
# ORQUESTADORES
# ==============================================

LISTA_ORQUESTADORES = reverse_lazy("robots:orquestadores")


class OrquestadorListView(ListView):
    template_name = "robots/orquestador_lista.html"
    context_object_name = "orquestadores"

    def get_queryset(self):
        return Orquestador.objects.prefetch_related("pasos__robot")


class OrquestadorDetailView(DetailView):
    model = Orquestador
    template_name = "robots/orquestador_detalle.html"
    context_object_name = "orquestador"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        orquestador = self.object
        contexto["pasos"] = orquestador.pasos.select_related("robot__credencial")
        contexto["problemas"] = orquestador.problemas()
        contexto["cadenas"] = orquestador.ejecuciones.select_related("solicitada_por")[:10]
        contexto["programaciones"] = orquestador.programaciones.all()
        return contexto


class OrquestadorCrearView(AdminRequeridoMixin, CreateView):
    model = Orquestador
    form_class = OrquestadorForm
    template_name = "core/formulario.html"
    extra_context = {"titulo": "Nuevo orquestador", "volver": LISTA_ORQUESTADORES}

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        messages.success(self.request, "Orquestador creado. Ahora agregue sus pasos.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("robots:orquestador", args=[self.object.pk])


class OrquestadorEditarView(AdminRequeridoMixin, UpdateView):
    model = Orquestador
    form_class = OrquestadorForm
    template_name = "core/formulario.html"
    extra_context = {"titulo": "Editar orquestador"}

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["volver"] = reverse("robots:orquestador", args=[self.object.pk])
        return contexto

    def form_valid(self, form):
        messages.success(self.request, "Orquestador actualizado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("robots:orquestador", args=[self.object.pk])


class OrquestadorEliminarView(AdminRequeridoMixin, DeleteView):
    model = Orquestador
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA_ORQUESTADORES
    extra_context = {"volver": LISTA_ORQUESTADORES}

    def form_valid(self, form):
        messages.success(self.request, "Orquestador eliminado.")
        return super().form_valid(form)


class OrquestadorEjecutarView(View):
    """Inicia la cadena (perfil Usuario y Administrador)."""

    def post(self, request, pk):
        orquestador = get_object_or_404(Orquestador, pk=pk)
        try:
            cadena = orquestacion.iniciar(orquestador, usuario=request.user)
        except orquestacion.OrquestadorNoDisponible as motivo:
            messages.error(request, str(motivo))
            return redirect("robots:orquestador", pk=pk)

        messages.success(request, f"Cadena #{cadena.pk} iniciada: se encoló el primer paso.")
        worker = EstadoWorker.obtener()
        if not worker.activo:
            messages.warning(
                request,
                f"El worker está {worker.get_estado_display().lower()}: la cadena "
                "quedará en cola hasta que se active (ver Monitor).",
            )
        return redirect("robots:cadena", pk=cadena.pk)


class PasoMixin(AdminRequeridoMixin, FormularioConParametrosMixin):
    form_class = PasoForm

    def get_volver(self):
        return reverse("robots:orquestador", args=[self.orquestador.pk])

    def guardar(self, form):
        paso = form.save(commit=False)
        paso.orquestador = self.orquestador
        if paso.orden is None:
            ultimo = self.orquestador.pasos.order_by("-orden").first()
            paso.orden = (ultimo.orden + 1) if ultimo else 1
        paso.save()
        messages.success(self.request, f"Paso {paso.orden} guardado.")
        return redirect(self.get_volver())


class PasoCrearView(PasoMixin, View):
    titulo = "Agregar paso"

    def dispatch(self, request, *args, pk=None, **kwargs):
        self.orquestador = get_object_or_404(Orquestador, pk=pk)
        return super().dispatch(request, *args, **kwargs)


class PasoEditarView(PasoMixin, View):
    titulo = "Editar paso"

    def dispatch(self, request, *args, pk=None, **kwargs):
        self.instancia = get_object_or_404(PasoOrquestador, pk=pk)
        self.orquestador = self.instancia.orquestador
        return super().dispatch(request, *args, **kwargs)


class PasoEliminarView(AdminRequeridoMixin, View):
    def post(self, request, pk):
        paso = get_object_or_404(PasoOrquestador, pk=pk)
        orquestador = paso.orquestador
        paso.delete()
        _renumerar(orquestador)
        messages.success(request, "Paso eliminado.")
        return redirect("robots:orquestador", pk=orquestador.pk)


class PasoMoverView(AdminRequeridoMixin, View):
    def post(self, request, pk):
        paso = get_object_or_404(PasoOrquestador, pk=pk)
        pasos = list(paso.orquestador.pasos.all())
        i = pasos.index(paso)
        j = i - 1 if request.POST.get("direccion") == "subir" else i + 1
        if 0 <= j < len(pasos):
            pasos[i], pasos[j] = pasos[j], pasos[i]
            _renumerar(paso.orquestador, pasos)
        return redirect("robots:orquestador", pk=paso.orquestador.pk)


def _renumerar(orquestador, pasos=None):
    pasos = pasos if pasos is not None else list(orquestador.pasos.all())
    for orden, paso in enumerate(pasos, start=1):
        if paso.orden != orden:
            PasoOrquestador.objects.filter(pk=paso.pk).update(orden=orden)


class CadenaDetailView(DetailView):
    model = EjecucionOrquestador
    context_object_name = "cadena"

    def get_queryset(self):
        return EjecucionOrquestador.objects.select_related(
            "orquestador", "solicitada_por", "programacion"
        )

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["robots/_cadena_estado.html"]
        return ["robots/cadena_detalle.html"]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        cadena = self.object
        ejecuciones = {e.paso_id: e for e in cadena.pasos.select_related("robot")}
        # Todos los pasos del orquestador, con su ejecución si ya se encoló
        filas = [(paso, ejecuciones.pop(paso.pk, None))
                 for paso in cadena.orquestador.pasos.select_related("robot")]
        # Ejecuciones de pasos que ya no existen en el orquestador
        filas += [(None, e) for e in ejecuciones.values()]
        contexto["filas"] = filas
        contexto["puede_cancelar"] = cadena.puede_cancelar(self.request.user)
        return contexto


class CadenaCancelarView(View):
    def post(self, request, pk):
        cadena = get_object_or_404(EjecucionOrquestador, pk=pk)
        if not cadena.puede_cancelar(request.user):
            raise PermissionDenied("No puede cancelar esta cadena.")
        orquestacion.cancelar(cadena, request.user)
        messages.info(request, "Cadena cancelada: no se ejecutarán más pasos.")
        return redirect("robots:cadena", pk=pk)
