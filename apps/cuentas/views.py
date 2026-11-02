from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import CambiarClaveForm, LoginForm, UsuarioForm
from .models import Usuario
from .permisos import AdminRequeridoMixin


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = "cuentas/login.html"
    redirect_authenticated_user = True


class CambiarClaveView(auth_views.PasswordChangeView):
    form_class = CambiarClaveForm
    template_name = "cuentas/cambiar_clave.html"
    success_url = reverse_lazy("core:panel")

    def form_valid(self, form):
        messages.success(self.request, "Contraseña actualizada.")
        return super().form_valid(form)


class UsuarioListView(AdminRequeridoMixin, ListView):
    model = Usuario
    template_name = "cuentas/usuario_lista.html"
    context_object_name = "usuarios"


class UsuarioCrearView(AdminRequeridoMixin, CreateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = "core/formulario.html"
    success_url = reverse_lazy("cuentas:lista")
    extra_context = {"titulo": "Nuevo usuario", "volver": success_url}

    def form_valid(self, form):
        messages.success(self.request, "Usuario creado.")
        return super().form_valid(form)


class UsuarioEditarView(AdminRequeridoMixin, UpdateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = "core/formulario.html"
    success_url = reverse_lazy("cuentas:lista")
    extra_context = {"titulo": "Editar usuario", "volver": success_url}

    def form_valid(self, form):
        messages.success(self.request, "Usuario actualizado.")
        return super().form_valid(form)
