from django.apps import AppConfig


class ProveedoresIpesaConfig(AppConfig):
    name = "apps.rpas.proveedores_ipesa"
    label = "rpa_proveedores_ipesa"
    verbose_name = "RPA Proveedores Ipesa"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
