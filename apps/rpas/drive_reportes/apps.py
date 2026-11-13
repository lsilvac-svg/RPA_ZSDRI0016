from django.apps import AppConfig


class DriveReportesConfig(AppConfig):
    name = "apps.rpas.drive_reportes"
    label = "rpa_drive_reportes"
    verbose_name = "RPA Subir reportes a Drive"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
