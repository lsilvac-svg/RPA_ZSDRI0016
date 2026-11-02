"""Genera el módulo de un robot nuevo en apps/rpas/<nombre>/.

Uso:
    python manage.py crear_rpa me2n --codigo ME2N --nombre "Pedidos ME2N"
"""
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PLANTILLAS = {
    "__init__.py": "",
    "apps.py": '''from django.apps import AppConfig


class {clase}Config(AppConfig):
    name = "apps.rpas.{modulo}"
    label = "rpa_{modulo}"
    verbose_name = "RPA {nombre}"

    def ready(self):
        from . import robot  # noqa: F401  (registra el robot)
''',
    "robot.py": '''"""{nombre}."""
from apps.robots.base import Resultado, RobotSAP
from apps.robots.parametros import Parametro, Tipo
from apps.robots.registro import registrar

# IDs de pantalla propios de este robot
# CAMPO_EJEMPLO = "wnd[0]/usr/ctxtCAMPO-LOW"


@registrar
class Robot{clase}(RobotSAP):
    codigo = "{codigo}"
    nombre = "{nombre}"
    descripcion = ""

    # Configuración permanente (Robots -> Configurar)
    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA, requerido=True),
    )
    # Datos que se piden al pulsar "Ejecutar"
    parametros_ejecucion = (
        Parametro("fecha_desde", "Fecha desde", Tipo.FECHA),
        Parametro("fecha_hasta", "Fecha hasta", Tipo.FECHA),
    )

    def carpetas_autorizadas(self, config):
        return [config["carpeta_exportacion"]]

    def ejecutar(self, ctx):
        ctx.paso("Abrir transacción", lambda: ctx.sesion.comando("/n{codigo}"))
        # TODO: completar los pasos del robot
        return Resultado(mensaje="Proceso completado")
''',
    "tests.py": '''from django.test import SimpleTestCase

from apps.robots import registro


class Robot{clase}Tests(SimpleTestCase):
    def test_esta_registrado(self):
        self.assertIn("{codigo}", registro.todos())
''',
}


class Command(BaseCommand):
    help = "Crea el módulo de un robot nuevo en apps/rpas/<modulo>/."

    def add_arguments(self, parser):
        parser.add_argument("modulo", help="Nombre del módulo en minúsculas, p. ej. me2n")
        parser.add_argument("--codigo", required=True, help="Código único del robot, p. ej. ME2N")
        parser.add_argument("--nombre", required=True, help="Nombre visible en la interfaz")

    def handle(self, *args, modulo, codigo, nombre, **options):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", modulo):
            raise CommandError("El módulo debe estar en minúsculas, sin espacios ni guiones.")

        carpeta = settings.CARPETA_RPAS / modulo
        if carpeta.exists():
            raise CommandError(f"Ya existe {carpeta}")

        clase = "".join(parte.capitalize() for parte in modulo.split("_"))
        valores = {"modulo": modulo, "codigo": codigo.upper(), "nombre": nombre, "clase": clase}

        carpeta.mkdir(parents=True)
        for archivo, plantilla in PLANTILLAS.items():
            (carpeta / archivo).write_text(plantilla.format(**valores), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Robot creado en {carpeta}"))
        self.stdout.write(
            "Completar robot.py y reiniciar la web y el worker: "
            "el módulo se detecta automáticamente."
        )
