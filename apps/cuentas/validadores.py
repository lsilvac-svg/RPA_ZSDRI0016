from django.conf import settings
from django.core.exceptions import ValidationError


def dominio_permitido(email):
    return email.strip().lower().endswith(f"@{settings.DOMINIO_CORREO}")


def validar_dominio(email):
    if not dominio_permitido(email):
        raise ValidationError(
            f"Solo se permiten correos @{settings.DOMINIO_CORREO}.",
            code="dominio_no_permitido",
        )
