from django.apps import AppConfig


class Fbl1nAnticiposConfig(AppConfig):
    name = "apps.rpas.fbl1n_anticipos"
    label = "rpa_fbl1n_anticipos"
    verbose_name = "RPA Anticipos FBL1N"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
