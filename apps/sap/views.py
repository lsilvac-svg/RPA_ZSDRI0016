from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from apps.cuentas.permisos import AdminRequeridoMixin

from .forms import ConexionSAPForm, CredencialSAPForm
from .models import ConexionSAP, CredencialSAP

LISTA = reverse_lazy("sap:lista")


class ConexionListView(AdminRequeridoMixin, TemplateView):
    """Conexiones (sistemas SAP) y logins con los robots que usa cada uno."""

    template_name = "sap/conexion_lista.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["conexiones"] = ConexionSAP.objects.annotate(
            num_credenciales=Count("credenciales")
        )
        contexto["credenciales"] = CredencialSAP.objects.select_related(
            "conexion"
        ).prefetch_related("robots")
        return contexto


class _GuardarMixin:
    mensaje = ""

    def form_valid(self, form):
        messages.success(self.request, self.mensaje)
        return super().form_valid(form)


class _EliminarMixin:
    mensaje = ""
    mensaje_protegido = ""

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, self.mensaje_protegido)
            return redirect(LISTA)
        messages.success(self.request, self.mensaje)
        return response


# --- Conexiones -------------------------------------------------------

class ConexionCrearView(AdminRequeridoMixin, _GuardarMixin, CreateView):
    model = ConexionSAP
    form_class = ConexionSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Nueva conexión SAP", "volver": LISTA}
    mensaje = "Conexión SAP creada. Agregue ahora un login para ella."


class ConexionEditarView(AdminRequeridoMixin, _GuardarMixin, UpdateView):
    model = ConexionSAP
    form_class = ConexionSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Editar conexión SAP", "volver": LISTA}
    mensaje = "Conexión SAP actualizada."


class ConexionEliminarView(AdminRequeridoMixin, _EliminarMixin, DeleteView):
    model = ConexionSAP
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA
    extra_context = {"volver": LISTA}
    mensaje = "Conexión SAP eliminada."
    mensaje_protegido = "No se puede eliminar: la conexión tiene logins SAP. Elimínelos primero."


# --- Logins -----------------------------------------------------------

class CredencialCrearView(AdminRequeridoMixin, _GuardarMixin, CreateView):
    model = CredencialSAP
    form_class = CredencialSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Nuevo login SAP", "volver": LISTA}
    mensaje = "Login SAP creado. Asígnelo a los robots en Robots → Configurar."

    def get_initial(self):
        inicial = super().get_initial()
        if conexion := self.request.GET.get("conexion"):
            inicial["conexion"] = conexion
        return inicial


class CredencialEditarView(AdminRequeridoMixin, _GuardarMixin, UpdateView):
    model = CredencialSAP
    form_class = CredencialSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Editar login SAP", "volver": LISTA}
    mensaje = "Login SAP actualizado."


class CredencialEliminarView(AdminRequeridoMixin, _EliminarMixin, DeleteView):
    model = CredencialSAP
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA
    extra_context = {"volver": LISTA}
    mensaje = "Login SAP eliminado."
    mensaje_protegido = "No se puede eliminar: hay robots que usan este login. Asígneles otro primero."
