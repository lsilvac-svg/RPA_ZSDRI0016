# Plataforma de RPAs SAP – IPESA

Plataforma web en Django para alojar, configurar, ejecutar y monitorear robots (RPA) que trabajan sobre **SAP GUI** mediante SAP GUI Scripting. Todo se controla desde una interfaz administrativa con menú lateral, sin tocar código. Cada robot es un **módulo independiente** que reutiliza el motor SAP común.

El primer robot incluido es **ZSDRI0016** (Reporte SD-FI de Venta Unidades Repuestos y Servicios), que exporta el periodo a Excel en una carpeta compartida.

## Funcionalidades

- **Panel:** indicadores del día, últimas ejecuciones y próximas programaciones.
- **Monitor:** estado del worker, ejecución en curso con su log en vivo, cola y finalizadas recientes. Se actualiza solo cada 3 segundos.
- **Ejecuciones:** historial con filtros, detalle con log completo, captura de pantalla del error, cancelar y reintentar.
- **Robots:** catálogo y "Ejecutar ahora" con parámetros (por ejemplo, rango de fechas).
- **Programaciones:** ejecuciones automáticas diarias, semanales o mensuales.
- **Conexiones SAP:** sistemas (entradas de SAP Logon) y sus **logins** (usuario + contraseña cifrada en la base de datos). Cada robot elige con qué login entra, así distintos RPAs pueden usar usuarios SAP diferentes.
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
  sap/                     Conexiones SAP y logins (modelos + pantallas)
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
2. Si el usuario SAP ya tiene sesión en este equipo, abre un modo nuevo dentro de ella. Si no, inicia sesión. Si la sesión está en otro equipo, la finaliza según la configuración del login.
3. Responde la ventana **Seguridad SAP GUI**: marca "Recordar mi decisión" y pulsa "Permitir", solo para las carpetas del robot; cualquier otro acceso lo rechaza.
4. Registra cada paso en el log, verifica la barra de estado y permite cancelar entre pasos.
5. Ante un error toma una captura de pantalla y reintenta. No reintenta errores definitivos como una contraseña incorrecta, para no bloquear el usuario SAP.
6. Al final **siempre cierra la sesión SAP**, haya terminado bien o con error.

## Cómo levantar el proyecto

Hay dos modos. Ambos usan el mismo código y el mismo `.env`; solo cambia `DB_ENGINE`.

| Modo                       | `DB_ENGINE` | Web                              | Base de datos            | Uso                        |
|----------------------------|-------------|----------------------------------|--------------------------|----------------------------|
| **Docker** (recomendado)   | `postgres`  | Contenedor `web` (waitress, 8030) | Contenedor `db` (PostgreSQL 17) | Producción en el equipo del robot |
| **Sin Docker**             | `sqlite`    | `scripts\iniciar_web.bat`         | `db.sqlite3` (modo WAL)  | Desarrollo y pruebas        |

En los dos modos, el **worker** corre en Windows, fuera de Docker.

### 1. Requisitos previos

| Requisito | Detalle |
|-----------|---------|
| Windows 10/11 | Con una **sesión de escritorio iniciada** por el usuario que tiene mapeada la unidad `Z:`. |
| SAP GUI 8.x | Ruta por defecto `C:\Program Files\SAP\FrontEnd\SAPgui\saplogon.exe` (se puede cambiar en cada conexión SAP). La entrada de SAP Logon (p. ej. `PRD_HANA`) debe existir. |
| SAP GUI Scripting en el **servidor** | Parámetro `sapgui/user_scripting = TRUE` (lo habilita Basis). |
| SAP GUI Scripting en el **cliente** | SAP Logon → Opciones → Accesibilidad y scripts → Scripting → marcar **Habilitar scripting**. Los avisos "Un script está intentando acceder…" los desactiva el robot solo. |
| Python **3.14** | Debe coincidir con la imagen Docker (`python:3.14-slim`). |
| Docker Desktop | Solo para el modo Docker. Debe estar **abierto** antes de `docker compose`. |

### 2. Entorno Python (ambos modos)

El venv es necesario también en modo Docker, porque el worker y los comandos de administración corren en Windows.

```powershell
cd C:\Users\<usuario>\Desktop\RPA\SAP\RPA_ZSDRI0016
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Archivo `.env`

```powershell
Copy-Item .env.example .env
```

Completar los valores **en este orden**. `generar_clave_cifrado` carga Django, así que falla si todavía no hay `DJANGO_SECRET_KEY`.

```powershell
# a) DJANGO_SECRET_KEY
.\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"

# b) RPA_CLAVE_CIFRADO (con DJANGO_SECRET_KEY ya guardada en .env)
.\venv\Scripts\python.exe manage.py generar_clave_cifrado

# c) DB_PASSWORD (solo modo Docker)
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(24))"
```

| Variable | Valor |
|----------|-------|
| `DB_ENGINE` | `postgres` (Docker) o `sqlite` (sin Docker) |
| `DB_HOST` | `127.0.0.1`. Lo usa el worker desde Windows; el contenedor web lo reemplaza por `db` automáticamente. |
| `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` | Agregar el nombre o IP del equipo si se accede desde otras PCs (p. ej. `http://PC-RPA:8030`). |
| `DJANGO_DEBUG` | `0`. Los estáticos los sirve WhiteNoise, no hace falta `1`. |

> **Respaldar `.env`.** Si se pierde `RPA_CLAVE_CIFRADO`, las contraseñas SAP guardadas no se pueden descifrar y hay que ingresarlas de nuevo.

### 4A. Levantar con Docker

```powershell
# 1. Web + PostgreSQL. El entrypoint aplica migraciones y collectstatic.
docker compose up -d --build
docker compose ps                  # esperar db "healthy" y web "running"

# 2. Superadministrador (se conecta a PostgreSQL por 127.0.0.1:5432)
.\venv\Scripts\python.exe manage.py crear_superadmin

# 3. Worker como tarea programada (arranca oculto al iniciar sesión en Windows)
powershell -ExecutionPolicy Bypass -File scripts\instalar_worker.ps1
```

Comandos habituales:

```powershell
docker compose up -d --build      # actualizar tras cambios de código
docker compose logs -f web        # logs de la web
docker compose down               # detener (los datos quedan en el volumen pgdata)
```

- PostgreSQL se publica solo en `127.0.0.1:5432`, para el worker de este equipo.
- La web escucha en `0.0.0.0:8030`.
- `./media` y `./logs` se montan en el contenedor: las capturas que guarda el worker se ven desde la web.

### 4B. Levantar sin Docker (SQLite)

Con `DB_ENGINE=sqlite` en `.env`:

```powershell
.\venv\Scripts\python.exe manage.py migrate            # crea db.sqlite3
.\venv\Scripts\python.exe manage.py crear_superadmin
scripts\iniciar_web.bat        # http://localhost:8030 (deja la consola abierta)
scripts\iniciar_worker.bat     # en otra consola; o instalar_worker.ps1 para dejarlo como tarea
```

### 5. Verificar que quedó funcionando

1. Abrir http://localhost:8030 e ingresar con `SUPERADMIN_EMAIL` y la contraseña creada.
2. **Monitor:** el worker debe figurar como **Activo**, con el nombre del equipo. Si dice **No iniciado**, ver [Solución de problemas](#solución-de-problemas).
3. **Robots:** debe aparecer **Ventas ZSDRI0016**. Los robots se registran solos al abrir esta pantalla o al iniciar el worker.

### 6. Configuración inicial desde la web (como administrador)

1. **Conexiones SAP:** crear la conexión (p. ej. conexión en SAP Logon `PRD_HANA`) y agregarle uno o más **logins** (usuario y contraseña). Use un login distinto para cada grupo de RPAs que deba entrar con otro usuario.
2. **Robots → Configurar:** elegir el **login SAP** del robot y revisar los parámetros (ver [Robot ZSDRI0016](#robot-zsdri0016)).
3. **Usuarios:** dar de alta al equipo.
4. **Programaciones** (opcional): por ejemplo, el ZSDRI0016 el día 1 de cada mes a las 07:00.
5. **Prueba:** Robots → Ejecutar ahora y seguir el log en el **Monitor**.

### Actualizar tras cambios de código

```powershell
git pull
.\venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d --build                                # web (migra sola)
Stop-ScheduledTask  -TaskName "RPA SAP - Worker"            # reiniciar worker
Start-ScheduledTask -TaskName "RPA SAP - Worker"
```

En modo sin Docker: `manage.py migrate` y reiniciar los dos `.bat`.

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

Parámetros de cada ejecución (al ejecutar a mano, en cada programación y en cada paso de orquestador):

| Parámetro               | Uso                                                                 |
|-------------------------|---------------------------------------------------------------------|
| Periodo                 | **Mes anterior completo** (defecto) o **Mes en curso** (del día 1 a hoy). |
| Fecha desde / hasta     | Opcionales: si se indican, reemplazan el inicio / fin del periodo.  |
| Nombre fijo del archivo | P. ej. `Ventas_Mes_Actual` → siempre `Ventas_Mes_Actual.xlsx`, reemplazado en cada ejecución, para que el origen de datos de Excel/Power BI no cambie. Vacío = prefijo + periodo. |

Ejemplo: programación diaria a las 07:00 con *Periodo = Mes en curso* y *Nombre fijo = Ventas_Mes_Actual*.

## Orquestadores

Menú **Orquestadores**: cadenas de robots que se ejecutan una tras otra. Se pueden crear varios.

- Cada paso es un robot con sus propios parámetros de ejecución. El orden se cambia con las flechas.
- Al ejecutar (a mano o con una programación) se encola el paso 1. **El paso siguiente se encola si el anterior terminó *Exitoso* o *Sin datos***; si falla o se cancela, la cadena queda **Detenida** (o *Cancelada*) y no corren los pasos restantes.
- El paso siguiente corre apenas termina el anterior: hereda el lugar de la cadena en la cola y no espera detrás de ejecuciones encoladas mientras tanto.
- Un orquestador no se puede iniciar si ya tiene una cadena en curso, si no tiene pasos o si algún robot está inactivo, sin login SAP u ocupado.

**Sin encolamientos duplicados:** un robot no se encola (programación, ejecución manual, reintento o inicio de cadena) si ya está en cola, ejecutándose o tiene un paso pendiente en una cadena activa. La programación omitida queda en el log del worker y se reprograma para su siguiente fecha.
- En **Cadena #N** se ve el avance paso a paso (se actualiza solo) y se puede cancelar la cadena.
- En **Programaciones** hay dos botones:
  - **Programar robot**: un robot suelto, con sus parámetros de ejecución.
  - **Programar orquestador**: solo se elige el orquestador, la frecuencia y la hora. No se piden parámetros por robot: a esa hora arranca la cadena y todos sus robots corren en el orden de los pasos, cada uno con los parámetros definidos en su paso. No hace falta programar cada robot por separado.

## Robot Anticipos FBL1N

Partidas de proveedores (FBL1N) con **operaciones CME** y **partidas memo** marcadas, exportadas a Excel (`xlsx`).

| Parámetro (Robots → Configurar)  | Valor por defecto                                   |
|----------------------------------|-----------------------------------------------------|
| Carpeta de exportación           | `Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP` |
| Nombre del archivo               | `Anticipos_FBL1N_2026` (cada ejecución reemplaza el archivo) |
| Agregar la fecha clave al nombre | No (Sí → `Anticipos_FBL1N_2026_20261112.xlsx`)      |
| Sociedad                         | `PE01`                                              |
| Variante de disposición          | `/CXP EDWIN` (obligatoria; nombre exacto de la variante en SAP) |
| Abrir y cerrar Excel             | Sí / Sí                                             |

Al ejecutarlo se puede indicar la **fecha clave** (partidas abiertas a esa fecha); vacía = hoy. La unidad `Y:` debe estar mapeada en la sesión de Windows del worker.

## Robot Partidas de clientes FBL5N

Partidas de clientes (FBL5N) con **operaciones CME** y **partidas memo** marcadas, exportadas a Excel (`xlsx`) con **nombre fijo**. De la grabación original solo se usa la segunda descarga (*Lista → Exportar → Hoja de cálculo*, formato `xlsx-TT`); la primera (*Grabar → Fichero local*) no funcionaba y se eliminó.

| Parámetro (Robots → Configurar)  | Valor por defecto                                   |
|----------------------------------|-----------------------------------------------------|
| Carpeta de exportación           | `Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP` |
| Nombre del archivo               | `Archivo_FBL5N` → `Archivo_FBL5N.xlsx` (cada ejecución lo reemplaza) |
| Sociedad                         | `PE01`                                              |
| Operaciones CME / Partidas memo  | Sí / Sí                                             |
| Variante de disposición          | `/CXC EDWIN` (obligatoria; nombre exacto de la variante en SAP) |
| Tiempo máximo del reporte        | 900 s                                               |
| Abrir y cerrar Excel             | Sí / Sí                                             |

Al ejecutarlo se puede indicar la **fecha clave** (partidas abiertas a esa fecha); vacía = hoy.

## Robot Proveedores Ipesa

Reporte `ZMMRI0017` (lista de proveedores) filtrado por fecha de modificación (`S_AEDAT`), exportado a Excel.

| Parámetro (Robots → Configurar)  | Valor por defecto                                   |
|----------------------------------|-----------------------------------------------------|
| Carpeta de exportación           | `Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\LISTA_PROVEEDORES` |
| Prefijo del archivo              | `Proveedores_Ipesa` → `Proveedores_Ipesa_202610.xlsx` |
| Valor del primer campo           | Vacío: se elige la fila 4 de la lista F4 del campo donde SAP deja el cursor, como en la grabación. El log indica qué campo y qué valor; conviene escribir ese valor aquí. |
| Abrir y cerrar Excel             | Sí / Sí                                             |

Al ejecutarlo, si se dejan vacías las fechas de modificación se usa **el mes anterior completo**.

## Robot Subir reportes a Drive

No abre SAP (no necesita login SAP). Usa una **cuenta de servicio de Google** (menú *Cuentas de Google*: se sube su clave JSON, que se guarda cifrada).

| Parte | Origen (el archivo más reciente) | Destino | Comportamiento |
|-------|----------------------------------|---------|----------------|
| Proveedores | `Y:\…\MASIVO\LISTA_PROVEEDORES\Proveedores_Ipesa_*.xlsx` | Hoja de Google Sheets, pestaña `Proveedores` | **Actualiza**: por *Organización compras + Proveedor + Sector*, cambia las filas que variaron, agrega las nuevas y **conserva las históricas**. La columna `Actualizado RPA` indica cuándo cambió cada fila. |
| FBL1N | `Y:\…\MASIVO\REPORTE_SAP\Anticipos_FBL1N_*.xlsx` | Carpeta de Drive, archivo `Anticipos_FBL1N.xlsx` | **Reemplaza** el archivo completo (mismo enlace). |
| FBL5N | `Y:\…\MASIVO\REPORTE_SAP\Archivo_FBL5N*.xlsx` | Carpeta de Drive del FBL5N (vacía = la misma de FBL1N), archivo `Archivo_FBL5N.xlsx` | **Reemplaza** el archivo completo (mismo enlace), igual que FBL1N. |

Las tres partes son independientes: si una falla o no tiene archivo, las otras igual se procesan. Cada una se puede desactivar en *Configurar*.

Ejemplo de orquestador: *Anticipos FBL1N* → *Partidas de clientes FBL5N* → *Subir reportes a Drive*.

Configuración en Google Cloud (una vez):
1. Crear un proyecto y habilitar **Google Drive API** y **Google Sheets API**.
2. Crear una **cuenta de servicio** (sin roles) y descargar una **clave JSON**.
3. Compartir con el correo de la cuenta de servicio, como **Editor**, la hoja de Sheets de proveedores y la carpeta del reporte. La cuenta de servicio no tiene espacio en "Mi unidad": la carpeta del reporte debe estar en una **Unidad compartida**, o los archivos `Anticipos_FBL1N.xlsx` y `Archivo_FBL5N.xlsx` deben existir antes (subido a mano) para que el robot solo lo reemplace.
4. En la web: *Cuentas de Google → Nueva cuenta* (subir el JSON) y *Robots → Subir reportes a Drive → Configurar* (pegar la URL de la hoja y de la carpeta).

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

## Solución de problemas

| Síntoma | Causa probable / solución |
|---------|---------------------------|
| `ImproperlyConfigured: Falta DJANGO_SECRET_KEY` | `.env` no existe o la variable está vacía. Ver paso 3. |
| `Falta RPA_CLAVE_CIFRADO` al guardar una conexión SAP | Generarla con `manage.py generar_clave_cifrado` y reiniciar la web y el worker. |
| `No se pudo descifrar un secreto` | `RPA_CLAVE_CIFRADO` cambió. Volver a ingresar las contraseñas de los logins en **Conexiones SAP**. |
| `docker compose` → `Definir DB_PASSWORD en .env` | Falta `DB_PASSWORD` en `.env`. |
| `docker compose` no responde | Docker Desktop no está abierto. |
| El puerto 5432 u 8030 ya está en uso | Otro PostgreSQL u otra app. Detenerla o cambiar el puerto publicado en `docker-compose.yml`. |
| `crear_superadmin` o el worker no conectan a PostgreSQL | El contenedor `db` no está levantado (`docker compose ps`), o `DB_HOST` no es `127.0.0.1`. |
| Error 400 (Bad Request) al entrar desde otra PC | Agregar el host en `DJANGO_ALLOWED_HOSTS`. |
| Error 403 CSRF al iniciar sesión desde otra PC | Agregar `http://<host>:8030` en `DJANGO_CSRF_TRUSTED_ORIGINS`. |
| "Solo se permiten correos @ipesa.com.pe" | El login exige el dominio de `DOMINIO_CORREO`. |
| Monitor: worker **No iniciado** | No hay sesión de Windows iniciada, la tarea no está instalada o el proceso se cayó. Revisar `logs\worker_consola.log` y la tarea "RPA SAP - Worker" en el Programador de tareas. |
| `Ya hay un worker ejecutándose en este equipo` | Ya corre la tarea programada. Detenerla antes de usar `iniciar_worker.bat`. |
| Monitor: worker **Pausado** | Un administrador lo pausó. Pulsar **Activar worker**. |
| `SAP GUI Scripting no está habilitado` / el script fue rechazado | Habilitar el scripting en el cliente y en el servidor (ver requisitos). |
| `No se encontró SAP Logon en …` | Corregir la ruta de `saplogon.exe` en la conexión SAP. |
| `SAP solicita cambiar la contraseña` | Cambiarla manualmente en SAP y actualizarla en el login correspondiente de **Conexiones SAP**. |
| El Excel no se guarda en `Z:` | El worker corre con un usuario o sesión sin la unidad `Z:` mapeada. Por eso el worker no se instala como "ejecutar aunque el usuario no haya iniciado sesión". |
