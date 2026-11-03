# Plataforma de RPAs SAP – IPESA

Plataforma web en Django para alojar, configurar, ejecutar y monitorear robots (RPA) que trabajan sobre **SAP GUI** mediante SAP GUI Scripting. Todo se controla desde una interfaz administrativa con menú lateral, sin tocar código. Cada robot es un **módulo independiente** que reutiliza el motor SAP común.

El primer robot incluido es **ZSDRI0016** (Reporte SD-FI de Venta Unidades Repuestos y Servicios), que exporta el periodo a Excel en una carpeta compartida.

## Funcionalidades

- **Panel:** indicadores del día, últimas ejecuciones y próximas programaciones.
- **Monitor:** estado del worker, ejecución en curso con su log en vivo, cola y finalizadas recientes. Se actualiza solo cada 3 segundos.
- **Ejecuciones:** historial con filtros, detalle con log completo, captura de pantalla del error, cancelar y reintentar.
- **Robots:** catálogo y "Ejecutar ahora" con parámetros (por ejemplo, rango de fechas).
- **Programaciones:** ejecuciones automáticas diarias, semanales o mensuales.
- **Conexiones SAP:** sistemas y credenciales, con la contraseña cifrada en la base de datos.
- **Usuarios:** alta, edición y perfiles.

### Perfiles

| Perfil            | Puede                                                                                     |
|-------------------|-------------------------------------------------------------------------------------------|
| **Usuario**       | Ver panel, monitor y ejecuciones; ejecutar robots; cancelar **sus** ejecuciones.           |
| **Administrador** | Todo lo anterior, más configurar robots, conexiones SAP, programaciones y usuarios, y acceder al admin de Django. |

- Solo pueden iniciar sesión correos **@ipesa.com.pe**. Se valida al iniciar sesión y al crear usuarios.
- El superadministrador es **lsilvac@ipesa.com.pe**.

## Estructura

```
config/                    Configuración Django (settings, urls, wsgi)
apps/
  core/                    Layout con sidebar, panel, cifrado, estilos
  cuentas/                 Usuario por correo, perfiles, login por dominio
  sap/                     Conexiones SAP (modelo + pantallas)
    motor/                 Librería SAP GUI reutilizable (sin Django)
      conexion.py            abrir SAP Logon, login, sesión ya abierta, cierre
      sesion.py              esperas, escribir, presionar, barra de estado, capturas
      seguridad.py           respuesta a la ventana "Seguridad SAP GUI"
      alv.py                 variantes ALV y exportación a Excel
      archivos.py            carpetas de red, verificación de archivos, cerrar Excel
      fechas.py              periodos y formato de fecha SAP
      windows.py             único punto de acceso a pywin32
  robots/                  Framework de robots
    base.py                  RobotSAP (clase base) y ContextoEjecucion
    parametros.py            parámetros declarativos -> formularios automáticos
    registro.py              registro de robots instalados
    ejecutor.py              reintentos, estados, logs en BD, capturas
    planificador.py          programaciones
    worker.py                proceso que ejecuta la cola
  rpas/                    UN MÓDULO POR ROBOT (se detectan automáticamente)
    zsdri0016/               Robot ZSDRI0016: solo su lógica de negocio
docker/  Dockerfile  docker-compose.yml     Instancia Docker (web + PostgreSQL)
scripts/                   instalar_worker.ps1 (tarea programada), worker_oculto.pyw,
                           iniciar_web.bat / iniciar_worker.bat (sin Docker / depuración)
```

Cada app tiene sus propias plantillas (`templates/`) y pruebas (`tests.py`).

## Cómo funciona

La plataforma tiene dos procesos que comparten la misma base de datos:

| Proceso    | Dónde corre                        | Qué hace                                         |
|------------|------------------------------------|--------------------------------------------------|
| **Web**    | Docker (o Windows), puerto **8030** | Interfaz: encola ejecuciones, configura, monitorea |
| **Worker** | **Windows** con SAP GUI y escritorio | Toma la cola y opera SAP GUI, de a una ejecución |

El worker no puede ir en Docker: SAP GUI solo funciona en Windows, con sesión de escritorio, y necesita las unidades de red como `Z:`.

Cada ejecución, sin que el robot tenga que programarlo:
1. Abre SAP Logon si hace falta y desactiva el aviso "Un script está intentando acceder a SAP GUI".
2. Si el usuario SAP ya tiene sesión en este equipo, abre un modo nuevo dentro de ella. Si no, inicia sesión. Si la sesión está en otro equipo, la finaliza según la configuración de la conexión.
3. Responde la ventana **Seguridad SAP GUI**: marca "Recordar mi decisión" y pulsa "Permitir", solo para las carpetas del robot; cualquier otro acceso lo rechaza.
4. Registra cada paso en el log, verifica la barra de estado y permite cancelar entre pasos.
5. Ante un error toma una captura de pantalla y reintenta. No reintenta errores definitivos como una contraseña incorrecta, para no bloquear el usuario SAP.
6. Al final **siempre cierra la sesión SAP**, haya terminado bien o con error.

## Instalación

Requisitos: Windows con SAP GUI 8.x y SAP GUI Scripting habilitado (`sapgui/user_scripting = TRUE` en el servidor), Python 3.14 y Docker Desktop.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Completar en .env: DJANGO_SECRET_KEY, RPA_CLAVE_CIFRADO y DB_PASSWORD (ver comentarios)

docker compose up -d --build                   # web en http://localhost:8030 + PostgreSQL
.\venv\Scripts\python.exe manage.py crear_superadmin   # contraseña de lsilvac@ipesa.com.pe
powershell -ExecutionPolicy Bypass -File scripts\instalar_worker.ps1   # worker en Windows
```

Luego, desde la web (como administrador):
1. **Conexiones SAP:** crear la conexión. Por ejemplo, conexión en SAP Logon `PRD_HANA`, con usuario y contraseña.
2. **Robots → Configurar:** asignar la conexión y revisar los parámetros.
3. **Usuarios:** dar de alta al equipo.
4. **Programaciones** (opcional): por ejemplo, el ZSDRI0016 el día 1 de cada mes a las 07:00.

### Docker

```powershell
docker compose up -d --build      # levantar o actualizar tras cambios de código
docker compose ps                 # estado
docker compose logs -f web        # logs de la web
docker compose down               # detener (los datos quedan en el volumen pgdata)
```

- PostgreSQL se publica solo en `127.0.0.1:5432`, para el worker de este equipo.
- La web corre en `0.0.0.0:8030`. Para acceder desde otros equipos, agregar su nombre o IP en `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS`.

### Sin Docker (desarrollo)

Con `DB_ENGINE=sqlite` en `.env` todo corre en Windows con SQLite:

```powershell
scripts\iniciar_web.bat           # http://localhost:8030
scripts\iniciar_worker.bat
```

### Worker: arranque automático y control desde el panel

`scripts\instalar_worker.ps1` registra la tarea **"RPA SAP - Worker"** en el Programador de tareas de Windows:
- Se inicia al iniciar sesión del usuario actual.
- Corre oculto, sin ventana, con `pythonw`.
- Se reinicia solo si el proceso se cae.

Desde el **Monitor**, un administrador lo controla:

| Estado          | Significado                                                                   |
|-----------------|-------------------------------------------------------------------------------|
| **Activo**      | El proceso corre y procesa la cola.                                           |
| **Pausado**     | El proceso corre pero no toma ejecuciones nuevas (la que está en curso termina). Botón **Activar worker**. |
| **No iniciado** | El proceso no responde: no hay sesión de Windows iniciada o la tarea no está instalada. |

- Los botones **Pausar worker** y **Activar worker** del Monitor solo aparecen para administradores, y queda registrado quién hizo cada cambio.
- La web corre en Docker y no puede arrancar programas en Windows. Por eso el proceso arranca con la sesión de Windows y el panel lo activa o pausa.
- Para quitar la tarea: `powershell -ExecutionPolicy Bypass -File scripts\instalar_worker.ps1 -Desinstalar`.
- Para depurar, se puede usar `scripts\iniciar_worker.bat`, que muestra la consola, con la tarea detenida. El log del worker está en `logs\rpa.log` y su salida en `logs\worker_consola.log`.
- La tarea no se configura como "ejecutar aunque el usuario no haya iniciado sesión" porque sin escritorio SAP GUI no funciona y `Z:` no existe.
- Docker Desktop reinicia la web y la base solo, gracias a `restart: unless-stopped`.

## Cómo agregar un nuevo robot

```powershell
.\venv\Scripts\python.exe manage.py crear_rpa me2n --codigo ME2N --nombre "Pedidos ME2N"
```

Esto genera `apps/rpas/me2n/` con `apps.py`, `robot.py` y `tests.py`. Completar `robot.py`:

```python
@registrar
class RobotMe2n(RobotSAP):
    codigo = "ME2N"
    nombre = "Pedidos ME2N"

    # Configurables por un administrador desde la web
    parametros_config = (
        Parametro("carpeta_exportacion", "Carpeta de exportación", Tipo.CARPETA, requerido=True),
    )
    # Se piden al pulsar "Ejecutar"
    parametros_ejecucion = (
        Parametro("fecha_desde", "Fecha desde", Tipo.FECHA),
    )

    def carpetas_autorizadas(self, config):
        return [config["carpeta_exportacion"]]

    def ejecutar(self, ctx):
        ctx.paso("Abrir ME2N", lambda: ctx.sesion.comando("/nME2N"))
        ctx.paso("Ejecutar", lambda: ctx.sesion.tecla(8))
        destino = alv.exportar_excel(ctx.sesion, ctx.log, ctx.config["carpeta_exportacion"],
                                     "Pedidos", ctx.paso)
        return Resultado(mensaje="Exportado", archivo=str(destino))
```

Después, reiniciar el worker y la web (`docker compose up -d --build`). El robot aparece en **Robots** y su formulario de configuración se genera solo, sin tocar `settings.py`.

Al ejecutarse, el robot recibe `ctx` con:
- `ctx.sesion`: la sesión SAP lista para usar.
- `ctx.config` y `ctx.parametros`: los valores ya resueltos.
- `ctx.log`: el logger, cuyos mensajes se ven en la web.
- `ctx.paso(descripcion, accion)`: ejecuta una acción, la registra, valida la barra de estado y permite cancelar.

Para indicar el resultado, el robot lanza:
- `SinDatos`: periodo vacío; la ejecución no cuenta como error.
- `ErrorFatal`: error definitivo; no se reintenta.
- `ErrorSAP`: error recuperable; se reintenta.

## Robot ZSDRI0016

| Parámetro (Robots → Configurar)  | Valor actual                                        |
|----------------------------------|-----------------------------------------------------|
| Carpeta de exportación           | `Z:\Ventas 2026\Descarga_Ventas` (`Z:` = `\\serveripesa\TESORERIA\IPESA TESORERIA\Ventas`) |
| Prefijo del archivo              | `Reporte_ZSDRI0016` → `Reporte_ZSDRI0016_202610.xlsx` |
| Variante ALV / fila              | vacío / fila 5 ("VTA MAGA - TESORERIA")             |
| Transacción / texto menú / favorito | `ZSDRI0016` / `ZSDRI0016` / `F00007`            |
| Abrir y cerrar Excel             | Sí / Sí (no toca otros libros abiertos)             |

Al ejecutarlo, si se dejan vacías las fechas se usa **el mes anterior completo**.

## Pruebas

```powershell
.\venv\Scripts\python.exe manage.py test apps
```

Cubren login por dominio, perfiles, cifrado, programador, parámetros, ejecutor (éxito, sin datos, reintentos, cancelación), vistas y el robot ZSDRI0016. SAP se simula, así que no hace falta tenerlo abierto.

## Respaldos y archivos locales

- **Base de datos:** volumen Docker `pgdata`. Respaldo:
  `docker compose exec db pg_dump -U rpa_sap rpa_sap > respaldo.sql`
- **`.env`:** respaldarlo junto con la base, porque sin `RPA_CLAVE_CIFRADO` las contraseñas SAP no se pueden leer.
- **Logs:** `logs/rpa.log`, que rota a los 2 MB. El log de cada ejecución se ve en la web.
- **Capturas de errores:** `media/capturas/`.
