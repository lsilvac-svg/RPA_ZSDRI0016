from django import forms
from django.db.models import Q

from apps.core.forms import BootstrapFormMixin
from apps.sap.models import CredencialSAP

from . import registro
from .models import Ejecucion, Orquestador, PasoOrquestador, Programacion, Robot


class RobotForm(BootstrapFormMixin, forms.ModelForm):
    """Datos generales del robot; sus parámetros propios van en otro formulario."""

    class Meta:
        model = Robot
        fields = ["nombre", "descripcion", "credencial", "activo", "reintentos", "espera_entre_intentos"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Logins activos, más el actual aunque esté inactivo (para no perderlo al guardar)
        consulta = CredencialSAP.objects.select_related("conexion")
        filtro = Q(activa=True, conexion__activa=True)
        if self.instance.credencial_id:
            filtro |= Q(pk=self.instance.credencial_id)
        self.fields["credencial"].queryset = consulta.filter(filtro)
        self.fields["credencial"].empty_label = "Sin login SAP"


def robots_instalados():
    return Robot.objects.filter(codigo__in=list(registro.todos()))


def atributos_parametros(url, destino):
    """Atributos HTMX para recargar los parámetros al cambiar de robot."""
    return {
        "hx-get": url, "hx-target": destino, "hx-trigger": "change",
        "hx-include": "this",
    }


CAMPOS_HORARIO = ["nombre", "frecuencia", "hora", "dias_semana", "dia_mes", "activa"]


class HorarioFormMixin(BootstrapFormMixin, forms.ModelForm):
    """Frecuencia y hora comunes a las programaciones de robots y orquestadores."""

    dias_semana = forms.MultipleChoiceField(
        label="Días de la semana",
        choices=Programacion.DIAS_SEMANA,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Solo para frecuencia semanal.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["dias_semana"] = [str(d) for d in self.instance.dias_semana_lista]

    def clean_dias_semana(self):
        return ",".join(sorted(self.cleaned_data["dias_semana"]))

    def clean(self):
        datos = super().clean()
        frecuencia = datos.get("frecuencia")
        if frecuencia == Programacion.Frecuencia.SEMANAL and not datos.get("dias_semana"):
            self.add_error("dias_semana", "Seleccione al menos un día.")
        if frecuencia == Programacion.Frecuencia.MENSUAL:
            dia = datos.get("dia_mes")
            if not dia or not 1 <= dia <= 31:
                self.add_error("dia_mes", "Indique un día entre 1 y 31.")
        return datos


class ProgramacionForm(HorarioFormMixin):
    """Programación de un robot suelto, con sus parámetros de ejecución."""

    class Meta:
        model = Programacion
        fields = ["robot", *CAMPOS_HORARIO]
        widgets = {"hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, url_parametros=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["robot"].queryset = robots_instalados()
        self.fields["robot"].required = True
        if url_parametros:
            self.fields["robot"].widget.attrs.update(
                atributos_parametros(url_parametros, "#parametros-robot")
            )

    def save(self, commit=True):
        self.instance.orquestador = None
        return super().save(commit)


class ProgramacionOrquestadorForm(HorarioFormMixin):
    """Programación de un orquestador: a la hora indicada arranca la cadena y
    sus robots corren en el orden de sus pasos, con los parámetros de cada paso."""

    class Meta:
        model = Programacion
        fields = ["orquestador", *CAMPOS_HORARIO]
        widgets = {"hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, url_pasos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["orquestador"].queryset = Orquestador.objects.all()
        self.fields["orquestador"].required = True
        if url_pasos:
            self.fields["orquestador"].widget.attrs.update(
                atributos_parametros(url_pasos, "#pasos-orquestador")
            )

    def save(self, commit=True):
        self.instance.robot = None
        self.instance.parametros = {}
        return super().save(commit)


class OrquestadorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Orquestador
        fields = ["nombre", "descripcion", "activo"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}


class PasoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PasoOrquestador
        fields = ["robot"]

    def __init__(self, *args, url_parametros=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["robot"].queryset = robots_instalados()
        if url_parametros:  # PasoForm
            self.fields["robot"].widget.attrs.update(
                atributos_parametros(url_parametros, "#parametros-robot")
            )


class FiltroEjecucionesForm(BootstrapFormMixin, forms.Form):
    robot = forms.ModelChoiceField(Robot.objects.all(), required=False, empty_label="Todos los robots")
    estado = forms.ChoiceField(
        choices=[("", "Todos los estados"), *Ejecucion.Estado.choices], required=False
    )
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def filtrar(self, consulta):
        if not self.is_valid():
            return consulta
        datos = self.cleaned_data
        if datos["robot"]:
            consulta = consulta.filter(robot=datos["robot"])
        if datos["estado"]:
            consulta = consulta.filter(estado=datos["estado"])
        if datos["desde"]:
            consulta = consulta.filter(creada__date__gte=datos["desde"])
        if datos["hasta"]:
            consulta = consulta.filter(creada__date__lte=datos["hasta"])
        return consulta
