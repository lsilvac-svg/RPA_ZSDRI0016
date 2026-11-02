from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class AdminRequeridoMixin(UserPassesTestMixin):
    """Restringe una vista al perfil Administrador."""

    def test_func(self):
        return self.request.user.es_admin

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Solo disponible para administradores.")
        return super().handle_no_permission()


def exigir_admin(usuario):
    if not usuario.es_admin:
        raise PermissionDenied("Solo disponible para administradores.")
