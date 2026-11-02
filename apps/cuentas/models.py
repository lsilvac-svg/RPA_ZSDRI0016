from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .validadores import validar_dominio


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **campos):
        email = self.normalize_email(email).lower()
        validar_dominio(email)
        usuario = self.model(email=email, **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **campos):
        campos.setdefault("rol", Usuario.Rol.USUARIO)
        campos.setdefault("is_staff", False)
        campos.setdefault("is_superuser", False)
        return self._crear(email, password, **campos)

    def create_superuser(self, email, password=None, **campos):
        campos.update(rol=Usuario.Rol.ADMIN, is_staff=True, is_superuser=True)
        return self._crear(email, password, **campos)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class Usuario(AbstractUser):
    """Usuario identificado por su correo corporativo."""

    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        USUARIO = "USUARIO", "Usuario"

    username = None
    email = models.EmailField("correo", unique=True, validators=[validar_dominio])
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.USUARIO)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def es_admin(self):
        return self.is_superuser or self.rol == self.Rol.ADMIN

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        # Los administradores pueden entrar al admin de Django
        self.is_staff = self.es_admin
        super().save(*args, **kwargs)
