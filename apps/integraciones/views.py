from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.cuentas.permisos import AdminRequeridoMixin

from .forms import CuentaGoogleForm
from .models import CuentaGoogle

LISTA = reverse_lazy("integraciones:lista")


class CuentaListView(AdminRequeridoMixin, ListView):
    model = CuentaGoogle
    template_name = "integraciones/cuenta_lista.html"
    context_object_name = "cuentas"


class CuentaCrearView(AdminRequeridoMixin, CreateView):
    model = CuentaGoogle
    form_class = CuentaGoogleForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Nueva cuenta de Google", "volver": LISTA}

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(
            self.request,
            f"Cuenta creada. Comparta las carpetas y hojas de destino con {self.object.correo} "
            "como Editor.",
        )
        return respuesta


class CuentaEditarView(AdminRequeridoMixin, UpdateView):
    model = CuentaGoogle
    form_class = CuentaGoogleForm
    template_name = "core/formulario.html"
    success_url = LISTA
    extra_context = {"titulo": "Editar cuenta de Google", "volver": LISTA}

    def form_valid(self, form):
        messages.success(self.request, "Cuenta de Google actualizada.")
        return super().form_valid(form)


class CuentaEliminarView(AdminRequeridoMixin, DeleteView):
    model = CuentaGoogle
    template_name = "core/confirmar_eliminar.html"
    success_url = LISTA
    extra_context = {"volver": LISTA}

    def form_valid(self, form):
        messages.success(self.request, "Cuenta de Google eliminada.")
        return super().form_valid(form)
