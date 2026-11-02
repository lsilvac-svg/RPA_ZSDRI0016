"""Cifrado simétrico de secretos (contraseñas SAP) guardados en la BD.

La clave vive solo en .env (RPA_CLAVE_CIFRADO); sin ella los valores
guardados no se pueden leer.
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def generar_clave():
    return Fernet.generate_key().decode()


def _fernet():
    clave = settings.RPA_CLAVE_CIFRADO
    if not clave:
        raise ImproperlyConfigured(
            "Falta RPA_CLAVE_CIFRADO en .env. Generarla con: "
            "python manage.py generar_clave_cifrado"
        )
    return Fernet(clave.encode())


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ImproperlyConfigured(
            "No se pudo descifrar un secreto: RPA_CLAVE_CIFRADO cambió. "
            "Volver a ingresar las contraseñas desde la interfaz."
        )
