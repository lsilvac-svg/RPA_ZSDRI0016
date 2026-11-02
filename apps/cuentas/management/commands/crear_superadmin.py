import getpass

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cuentas.models import Usuario


class Command(BaseCommand):
    help = "Crea (o actualiza la contraseña de) el superadministrador SUPERADMIN_EMAIL."

    def handle(self, *args, **options):
        email = settings.SUPERADMIN_EMAIL
        clave = getpass.getpass(f"Contraseña para {email}: ")
        if clave != getpass.getpass("Repetir contraseña: "):
            raise CommandError("Las contraseñas no coinciden.")
        try:
            validate_password(clave)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages))

        usuario = Usuario.objects.filter(email=email).first()
        if usuario is None:
            Usuario.objects.create_superuser(email, clave)
            self.stdout.write(self.style.SUCCESS(f"Superadministrador {email} creado."))
        else:
            usuario.set_password(clave)
            usuario.is_superuser = True
            usuario.rol = Usuario.Rol.ADMIN
            usuario.is_active = True
            usuario.save()
            self.stdout.write(self.style.SUCCESS(f"Superadministrador {email} actualizado."))
