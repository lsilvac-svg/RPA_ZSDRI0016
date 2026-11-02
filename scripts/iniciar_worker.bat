@echo off
REM Inicia el worker que ejecuta los robots SAP.
REM Debe correr en una sesion de Windows con escritorio (SAP GUI lo necesita),
REM con el usuario que tiene la unidad Z: conectada.
cd /d "%~dp0.."
venv\Scripts\python.exe manage.py rpa_worker
