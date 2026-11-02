# Plataforma de RPAs SAP – IPESA

Plataforma web en Django para alojar, configurar, ejecutar y monitorear robots (RPA) que trabajan sobre **SAP GUI** mediante SAP GUI Scripting. Todo se controla desde una interfaz administrativa con menú lateral, sin tocar código.

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

## Arquitectura

```
config/                 Configuración Django (settings, urls)
apps/
  core/                 Layout, panel, cifrado, utilidades de formularios
  cuentas/              Usuario por correo, perfiles, login por dominio
  sap/                  Conexiones SAP (modelo + CRUD)
    motor/              Librería SAP GUI reutilizable (sin Django):
      conexion.py         abrir SAP Logon, login, sesión ya abierta, cierre
      sesion.py           esperas, escribir, presionar, barra de estado, capturas
      seguridad.py        respuesta automática a "Seguridad SAP GUI"
      alv.py              variantes ALV y exportación a Excel
      archivos.py         carpetas de red, verificación de archivos, cerrar Excel
      fechas.py           periodos y formato de fecha SAP
  robots/               Framework de robots:
      base.py             RobotSAP (clase base) y ContextoEjecucion
      parametros.py       parámetros declarativos -> formularios automáticos
      registro.py         registro de robots instalados
      ejecutor.py         reintentos, estados, logs en BD, capturas
      planificador.py     programaciones
      worker.py           proceso que ejecuta la cola
  rpa_zsdri0016/        Robot ZSDRI0016 (solo su lógica de negocio)
templates/  static/     Interfaz (Bootstrap 5 + HTMX)
scripts/                iniciar_web.bat, iniciar_worker.bat
```

**Funcionamiento:** la web solo **encola** ejecuciones. Un proceso aparte, el **worker**, las toma de a una y opera SAP GUI. El worker debe correr en una sesión de Windows con escritorio, porque SAP GUI necesita interfaz gráfica.

Cada ejecución, sin que el robot tenga que programarlo:
1. Abre SAP Logon si hace falta y desactiva el aviso "Un script está intentando acceder a SAP GUI".
2. Si el usuario SAP ya tiene sesión en este equipo, abre un modo nuevo dentro de ella. Si no, inicia sesión. Si la sesión está en otro equipo, la finaliza según la configuración de la conexión.
3. Responde la ventana **Seguridad SAP GUI**: marca "Recordar mi decisión" y pulsa "Permitir", solo para las carpetas del robot; cualquier otro acceso lo rechaza.
4. Registra cada paso en el log, verifica la barra de estado y permite cancelar entre pasos.
5. Ante un error toma una captura de pantalla y reintenta. No reintenta errores definitivos como una contraseña incorrecta, para no bloquear el usuario SAP.
6. Al final **siempre cierra la sesión SAP**, haya terminado bien o con error.

## Instalación

Requisitos: Windows con SAP GUI 8.x, SAP GUI Scripting habilitado (`sapgui/user_scripting = TRUE` en el servidor) y Python 3.14.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Completar en .env: DJANGO_SECRET_KEY y RPA_CLAVE_CIFRADO (ver comentarios del archivo)
python manage.py generar_clave_cifrado

python manage.py migrate
python manage.py crear_superadmin        # pide la contraseña de lsilvac@ipesa.com.pe
```

Luego, desde la web (como administrador):
1. **Conexiones SAP:** crear la conexión. Por ejemplo, conexión en SAP Logon `PRD_HANA`, con usuario y contraseña.
2. **Robots → Configurar:** asignar la conexión y revisar los parámetros.
3. **Usuarios:** dar de alta al equipo.
4. **Programaciones** (opcional): por ejemplo, el ZSDRI0016 el día 1 de cada mes a las 07:00.

> **Migración desde el script anterior (`app.py`):** `python manage.py importar_env_zsdri0016` crea la conexión SAP y la configuración del robot a partir de las variables del `.env` anterior (`USUARIO`, `PASS`, `CARPETA_EXPORTACION`, etc.). Después esas variables pueden borrarse del `.env`.

## Puesta en marcha

Se necesitan **dos procesos**:

```powershell
# 1) Interfaz web en http://localhost:8000
scripts\iniciar_web.bat

# 2) Worker que ejecuta los robots (en la sesión de Windows con SAP y la unidad Z:)
scripts\iniciar_worker.bat
```

Para que arranquen solos, crear dos tareas en el **Programador de tareas** de Windows con el desencadenador "Al iniciar sesión" del usuario que corre los robots.
- No usar "Ejecutar tanto si el usuario inició sesión como si no" para el worker: sin escritorio, SAP GUI no funciona y las unidades mapeadas como `Z:` no existen.
- Para acceder a la web desde otros equipos, agregar el nombre o la IP del equipo en `DJANGO_ALLOWED_HOSTS`.

En desarrollo se puede usar `python manage.py runserver` con `DJANGO_DEBUG=1`.

## Cómo agregar un nuevo RPA

Cada robot es una app de Django pequeña que reutiliza el motor SAP y el framework.

1. Crear la app, por ejemplo `apps/rpa_me2n/`, con `__init__.py`, `apps.py` y `robot.py`.
2. En `apps.py`, registrar el robot al cargar la app:

   ```python
   class RpaMe2nConfig(AppConfig):
       name = "apps.rpa_me2n"
       verbose_name = "RPA ME2N – Pedidos"

       def ready(self):
           from . import robot  # noqa: F401
   ```

3. En `robot.py`, declarar los parámetros y la lógica:

   ```python
   from apps.robots.base import Resultado, RobotSAP
   from apps.robots.parametros import Parametro, Tipo
   from apps.robots.registro import registrar
   from apps.sap.motor import alv

   @registrar
   class RobotME2N(RobotSAP):
       codigo = "ME2N"
       nombre = "Pedidos ME2N"
       descripcion = "Exporta pedidos de compra."

       # Configurables por un administrador desde la web
       parametros_config = (
           Parametro("carpeta", "Carpeta de exportación", Tipo.CARPETA, requerido=True),
       )
       # Se piden al pulsar "Ejecutar"
       parametros_ejecucion = (
           Parametro("fecha_desde", "Fecha desde", Tipo.FECHA),
       )

       def carpetas_autorizadas(self, config):
           return [config["carpeta"]]

       def ejecutar(self, ctx):
           ctx.paso("Abrir ME2N", lambda: ctx.sesion.comando("/nME2N"))
           # ... ctx.sesion.escribir(...), ctx.sesion.tecla(8), alv.exportar_excel(...)
           return Resultado(mensaje="Exportado", archivo="...")
   ```

4. Agregar `"apps.rpa_me2n"` a `INSTALLED_APPS` en [config/settings.py](config/settings.py) y reiniciar la web y el worker. El robot aparece en **Robots** y su formulario de configuración se genera solo.

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

| Parámetro (Robots → Configurar)  | Valor inicial                                       |
|----------------------------------|-----------------------------------------------------|
| Carpeta de exportación           | `Z:\Ventas 2026\Descarga_Ventas` (`Z:` = `\\serveripesa\TESORERIA\IPESA TESORERIA\Ventas`) |
| Prefijo del archivo              | `Reporte_ZSDRI0016` → `Reporte_ZSDRI0016_202610.xlsx` |
| Variante ALV / fila              | vacío / fila 5 ("VTA MAGA - TESORERIA")             |
| Transacción / texto menú / favorito | `ZSDRI0016` / `ZSDRI0016` / `F00007`            |
| Abrir y cerrar Excel             | Sí / Sí (no toca otros libros abiertos)             |

Al ejecutarlo, si se dejan vacías las fechas se usa **el mes anterior completo**.

## Pruebas

```powershell
python manage.py test apps
```

Cubren login por dominio, perfiles, cifrado, programador, parámetros, ejecutor (éxito, sin datos, reintentos, cancelación) y vistas. SAP se simula, así que no hace falta tenerlo abierto.

## Logs y archivos locales

- Log general: `logs/rpa.log`, que rota a los 2 MB. El log de cada ejecución se ve en la web.
- Capturas de errores: `media/capturas/`.
- Base de datos: `db.sqlite3`. Respaldarla junto con el `.env`, porque sin `RPA_CLAVE_CIFRADO` las contraseñas SAP no se pueden leer.
