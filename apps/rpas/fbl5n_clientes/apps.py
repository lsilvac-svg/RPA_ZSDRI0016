from django.apps import AppConfig


class Fbl5nClientesConfig(AppConfig):
    name = "apps.rpas.fbl5n_clientes"
    label = "rpa_fbl5n_clientes"
    verbose_name = "RPA Partidas de clientes FBL5N"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
