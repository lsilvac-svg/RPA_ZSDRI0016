from django.core.management.base import BaseCommand, CommandError

from apps.robots.worker import Worker, WorkerYaEnEjecucion


class Command(BaseCommand):
    help = (
        "Inicia el worker que ejecuta los robots (manuales y programados). "
        "Debe correr en una sesión de Windows con escritorio."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--intervalo", type=int, default=5,
            help="Segundos entre revisiones de la cola (por defecto 5).",
        )
        parser.add_argument(
            "--una-vez", action="store_true",
            help="Procesa la cola pendiente y termina.",
        )

    def handle(self, *args, **options):
        try:
            Worker(intervalo=options["intervalo"]).iniciar(una_vez=options["una_vez"])
        except WorkerYaEnEjecucion as error:
            raise CommandError(str(error))
        except KeyboardInterrupt:
            self.stdout.write("Worker detenido por el usuario.")
