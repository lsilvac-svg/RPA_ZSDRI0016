from django.core.management.base import BaseCommand

from apps.core.cifrado import generar_clave


class Command(BaseCommand):
    help = "Genera una clave para RPA_CLAVE_CIFRADO (copiarla en .env)."

    def handle(self, *args, **options):
        self.stdout.write(f"RPA_CLAVE_CIFRADO={generar_clave()}")
