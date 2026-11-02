from django import forms

from apps.core.forms import BootstrapFormMixin

from .models import Ejecucion, Programacion, Robot


class RobotForm(BootstrapFormMixin, forms.ModelForm):
    """Datos generales del robot; sus parámetros propios van en otro formulario."""

    class Meta:
        model = Robot
        fields = ["nombre", "descripcion", "conexion", "activo", "reintentos", "espera_entre_intentos"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}


class ProgramacionForm(BootstrapFormMixin, forms.ModelForm):
    dias_semana = forms.MultipleChoiceField(
        label="Días de la semana",
        choices=Programacion.DIAS_SEMANA,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Solo para frecuencia semanal.",
    )

    class Meta:
        model = Programacion
        fields = ["robot", "nombre", "frecuencia", "hora", "dias_semana", "dia_mes", "activa"]
        widgets = {"hora": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

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
