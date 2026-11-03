"""Configuración de la plataforma de RPAs SAP.

Los valores sensibles o propios de cada equipo se leen del archivo .env.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(nombre, defecto=None):
    valor = os.getenv(nombre, "").strip()
    return valor or defecto


def env_bool(nombre, defecto=False):
    valor = env(nombre)
    if valor is None:
        return defecto
    return valor.lower() in ("1", "true", "si", "sí", "yes")


SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "Falta DJANGO_SECRET_KEY en .env. Ver README (Instalación)."
    )

DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Clave Fernet con la que se cifran las contraseñas SAP en la base de datos
RPA_CLAVE_CIFRADO = env("RPA_CLAVE_CIFRADO")

# Solo pueden ingresar correos de este dominio
DOMINIO_CORREO = env("DOMINIO_CORREO", "ipesa.com.pe").lower()
SUPERADMIN_EMAIL = env("SUPERADMIN_EMAIL", "lsilvac@ipesa.com.pe").lower()

AUTH_USER_MODEL = "cuentas.Usuario"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Plataforma
    "apps.core",
    "apps.cuentas",
    "apps.sap",
    "apps.robots",
]

# Robots: cada carpeta de apps/rpas/ con apps.py es un módulo y se instala sola
CARPETA_RPAS = BASE_DIR / "apps" / "rpas"
INSTALLED_APPS += sorted(
    f"apps.rpas.{carpeta.name}"
    for carpeta in CARPETA_RPAS.iterdir()
    if (carpeta / "apps.py").is_file()
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.estado_worker",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL (Docker): la web en el contenedor y el worker en Windows
# comparten la misma base. SQLite: desarrollo local sin Docker.
if env("DB_ENGINE", "sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "rpa_sap"),
            "USER": env("DB_USER", "rpa_sap"),
            "PASSWORD": env("DB_PASSWORD"),
            # 127.0.0.1 y no localhost: en Windows localhost puede resolver
            # a IPv6 y Docker publica el puerto solo en IPv4
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    # Modo WAL: el worker escribe logs mientras la web los lee
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                "transaction_mode": "IMMEDIATE",
                "timeout": 20,
            },
        }
    }

CSRF_TRUSTED_ORIGINS = [
    origen for origen in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origen
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Capturas de pantalla de errores y otros archivos generados
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "core:panel"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CARPETA_LOGS = BASE_DIR / "logs"
CARPETA_LOGS.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s"},
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "simple"},
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": CARPETA_LOGS / "rpa.log",
            "maxBytes": 2_000_000,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "simple",
        },
    },
    "loggers": {
        "rpa": {"handlers": ["consola", "archivo"], "level": "INFO"},
    },
}
