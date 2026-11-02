from django.apps import AppConfig


class Zsdri0016Config(AppConfig):
    name = "apps.rpas.zsdri0016"
    label = "rpa_zsdri0016"
    verbose_name = "RPA ZSDRI0016 – Ventas"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
