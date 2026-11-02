from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.cuentas.permisos import AdminRequeridoMixin

from .forms import ConexionSAPForm
from .models import ConexionSAP

LISTA = reverse_lazy("sap:lista")


class ConexionListView(AdminRequeridoMixin, ListView):
    model = ConexionSAP
    template_name = "sap/conexion_lista.html"
    context_object_name = "conexiones"


class ConexionCrearView(AdminRequeridoMixin, CreateView):
    model = ConexionSAP
    form_class = ConexionSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Nueva conexión SAP", "volver": LISTA}

    def form_valid(self, form):
        messages.success(self.request, "Conexión SAP creada.")
        return super().form_valid(form)


class ConexionEditarView(AdminRequeridoMixin, UpdateView):
    model = ConexionSAP
    form_class = ConexionSAPForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Editar conexión SAP", "volver": LISTA}

    def form_valid(self, form):
        messages.success(self.request, "Conexión SAP actualizada.")
        return super().form_valid(form)


class ConexionEliminarView(AdminRequeridoMixin, DeleteView):
    model = ConexionSAP
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA
    extra_context = {"volver": LISTA}

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                "No se puede eliminar: hay robots que usan esta conexión.",
            )
            return redirect(LISTA)
        messages.success(self.request, "Conexión SAP eliminada.")
        return response
