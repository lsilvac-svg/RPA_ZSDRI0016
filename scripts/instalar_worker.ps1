<#
Registra el worker de RPAs SAP en el Programador de tareas de Windows:
- se inicia al iniciar sesión el usuario actual (SAP GUI necesita escritorio
  y la unidad Z: solo existe en su sesión);
- corre oculto, sin ventana de consola;
- se reinicia solo si el proceso se cae.

Una vez instalado, el worker se activa o pausa desde el panel web (Monitor).

Uso:      powershell -ExecutionPolicy Bypass -File scripts\instalar_worker.ps1
Quitar:   powershell -ExecutionPolicy Bypass -File scripts\instalar_worker.ps1 -Desinstalar
#>
param([switch]$Desinstalar)

$ErrorActionPreference = 'Stop'
$NombreTarea = 'RPA SAP - Worker'

if ($Desinstalar) {
    Stop-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
    Write-Host "Tarea '$NombreTarea' eliminada."
    return
}

$Base = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Base 'venv\Scripts\pythonw.exe'
$Lanzador = Join-Path $Base 'scripts\worker_oculto.pyw'
if (-not (Test-Path $Pythonw)) { throw "No se encontró $Pythonw (crear el venv primero)." }

$Usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Accion = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Lanzador`"" -WorkingDirectory $Base
$Disparador = New-ScheduledTaskTrigger -AtLogOn -User $Usuario
$Principal = New-ScheduledTaskPrincipal -UserId $Usuario -LogonType Interactive -RunLevel Limited
$Opciones = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $NombreTarea -Action $Accion -Trigger $Disparador `
    -Principal $Principal -Settings $Opciones `
    -Description 'Worker de la plataforma de RPAs SAP (se controla desde el panel web).' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $NombreTarea
Write-Host "Tarea '$NombreTarea' registrada para $Usuario e iniciada."
