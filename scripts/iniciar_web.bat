@echo off
REM Inicia la interfaz web de la plataforma de RPAs SAP en http://localhost:8030
REM (alternativa a Docker: docker compose up -d).
cd /d "%~dp0.."
venv\Scripts\python.exe manage.py migrate --noinput
venv\Scripts\python.exe manage.py collectstatic --noinput --verbosity 0
venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8030 config.wsgi:application
