"""Inicia el worker sin ventana de consola (lo usa la tarea programada).

pythonw.exe no tiene consola: la salida se guarda en logs/worker_consola.log.
El log detallado sigue en logs/rpa.log.
"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)

(BASE / "logs").mkdir(exist_ok=True)
salida = open(BASE / "logs" / "worker_consola.log", "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = salida

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from django.core.management import execute_from_command_line  # noqa: E402

execute_from_command_line(["manage.py", "rpa_worker"])
