"""Cliente mínimo de Google Drive y Sheets (API REST) con cuenta de servicio.

Errores:
- ErrorFatal: permisos, IDs inexistentes, cuota -> requieren revisión manual.
- ErrorSAP: red o errores temporales de Google -> el ejecutor reintenta.
(Se reutilizan las excepciones del motor por su semántica de reintento.)
"""
import json
import re
from urllib.parse import quote

from apps.sap.motor import ErrorFatal, ErrorSAP

ALCANCES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
DRIVE = "https://www.googleapis.com/drive/v3"
DRIVE_SUBIDA = "https://www.googleapis.com/upload/drive/v3"
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIEMPO_ESPERA = 120


def extraer_id(texto):
    """Acepta el ID o la URL completa de una carpeta, archivo u hoja."""
    texto = (texto or "").strip()
    for patron in (r"/d/([\w-]+)", r"/folders/([\w-]+)", r"[?&]id=([\w-]+)"):
        coincidencia = re.search(patron, texto)
        if coincidencia:
            return coincidencia.group(1)
    return texto


class ClienteGoogle:
    def __init__(self, info_clave, sesion_http=None):
        self.correo = info_clave.get("client_email", "")
        if sesion_http is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account

            credenciales = service_account.Credentials.from_service_account_info(
                info_clave, scopes=ALCANCES
            )
            sesion_http = AuthorizedSession(credenciales)
        self.http = sesion_http

    # --- HTTP ----------------------------------------------------------

    def _pedir(self, metodo, url, que, **kwargs):
        import requests
        from google.auth.exceptions import RefreshError, TransportError

        try:
            respuesta = self.http.request(metodo, url, timeout=TIEMPO_ESPERA, **kwargs)
        except RefreshError as error:
            raise ErrorFatal(f"Google rechazó la clave de la cuenta de servicio: {error}")
        except (requests.RequestException, TransportError) as error:
            raise ErrorSAP(f"Sin conexión con Google al {que}: {error}")

        if respuesta.status_code < 400:
            return respuesta.json() if respuesta.content else {}

        detalle = _detalle_error(respuesta)
        if respuesta.status_code in (429, 500, 502, 503, 504):
            raise ErrorSAP(f"Google no respondió al {que} ({respuesta.status_code}): {detalle}")
        if respuesta.status_code in (403, 404):
            if "storageQuotaExceeded" in respuesta.text:
                raise ErrorFatal(
                    f"No se pudo {que}: una cuenta de servicio no tiene espacio propio en "
                    "'Mi unidad'. Use una carpeta de una Unidad compartida, o cree el "
                    "archivo una vez a mano en la carpeta para que el robot solo lo reemplace"
                )
            raise ErrorFatal(
                f"Sin acceso al {que} ({respuesta.status_code}: {detalle}). Verifique el ID "
                f"y que esté compartido con {self.correo} como Editor"
            )
        raise ErrorFatal(f"Google rechazó el {que} ({respuesta.status_code}): {detalle}")

    # --- Drive ---------------------------------------------------------

    def buscar_archivo(self, carpeta_id, nombre):
        nombre_escapado = nombre.replace("\\", "\\\\").replace("'", "\\'")
        consulta = f"'{carpeta_id}' in parents and name = '{nombre_escapado}' and trashed = false"
        datos = self._pedir(
            "GET", f"{DRIVE}/files", "buscar el archivo en Drive",
            params={
                "q": consulta, "fields": "files(id,name,webViewLink)",
                "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            },
        )
        archivos = datos.get("files", [])
        return archivos[0] if archivos else None

    def verificar_carpeta(self, carpeta_id):
        datos = self._pedir(
            "GET", f"{DRIVE}/files/{carpeta_id}", "leer la carpeta de Drive",
            params={"fields": "id,name,mimeType", "supportsAllDrives": "true"},
        )
        if datos.get("mimeType") != "application/vnd.google-apps.folder":
            raise ErrorFatal(f"El ID {carpeta_id} de Drive no es una carpeta")
        return datos

    def reemplazar_archivo(self, carpeta_id, nombre, contenido, tipo=TIPO_XLSX):
        """Sube `contenido` como `nombre` en la carpeta; si ya existe, lo reemplaza
        (mismo archivo y mismo enlace). Devuelve (archivo, creado)."""
        self.verificar_carpeta(carpeta_id)
        existente = self.buscar_archivo(carpeta_id, nombre)
        campos = {"fields": "id,name,webViewLink", "supportsAllDrives": "true"}

        if existente:
            archivo = self._pedir(
                "PATCH", f"{DRIVE_SUBIDA}/files/{existente['id']}", "reemplazar el archivo en Drive",
                params={**campos, "uploadType": "media"},
                data=contenido, headers={"Content-Type": tipo},
            )
            return archivo, False

        limite = "rpa_limite_subida"
        metadatos = json.dumps({"name": nombre, "parents": [carpeta_id]})
        cuerpo = (
            f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadatos}\r\n"
            f"--{limite}\r\nContent-Type: {tipo}\r\n\r\n"
        ).encode() + contenido + f"\r\n--{limite}--".encode()
        archivo = self._pedir(
            "POST", f"{DRIVE_SUBIDA}/files", "subir el archivo a Drive",
            params={**campos, "uploadType": "multipart"},
            data=cuerpo, headers={"Content-Type": f"multipart/related; boundary={limite}"},
        )
        return archivo, True

    # --- Sheets --------------------------------------------------------

    def asegurar_pestana(self, hoja_id, pestana):
        datos = self._pedir(
            "GET", f"{SHEETS}/{hoja_id}", "leer la hoja de Google Sheets",
            params={"fields": "properties.title,sheets.properties.title"},
        )
        titulos = [h["properties"]["title"] for h in datos.get("sheets", [])]
        if pestana not in titulos:
            self._pedir(
                "POST", f"{SHEETS}/{hoja_id}:batchUpdate", "crear la pestaña en la hoja",
                json={"requests": [{"addSheet": {"properties": {"title": pestana}}}]},
            )
        return datos.get("properties", {}).get("title", "")

    def leer_valores(self, hoja_id, pestana):
        datos = self._pedir(
            "GET", f"{SHEETS}/{hoja_id}/values/{quote(_rango(pestana), safe='')}",
            "leer la hoja de Google Sheets",
            params={"valueRenderOption": "UNFORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"},
        )
        return datos.get("values", [])

    def asegurar_tamano(self, hoja_id, pestana, filas, columnas):
        """Amplía la cuadrícula de la pestaña si es menor que filas x columnas.

        Google rechaza escribir fuera de la cuadrícula (una hoja nueva trae
        1000 filas y 26 columnas).
        """
        datos = self._pedir(
            "GET", f"{SHEETS}/{hoja_id}", "leer el tamaño de la hoja",
            params={"fields": "sheets.properties(sheetId,title,gridProperties)"},
        )
        propiedades = next(
            (h["properties"] for h in datos.get("sheets", []) if h["properties"]["title"] == pestana),
            None,
        )
        if propiedades is None:
            raise ErrorFatal(f"No existe la pestaña '{pestana}' en la hoja")
        cuadricula = propiedades.get("gridProperties", {})
        nuevas = {
            "rowCount": max(filas, cuadricula.get("rowCount", 0)),
            "columnCount": max(columnas, cuadricula.get("columnCount", 0)),
        }
        if (nuevas["rowCount"], nuevas["columnCount"]) == (
            cuadricula.get("rowCount"), cuadricula.get("columnCount")
        ):
            return
        self._pedir(
            "POST", f"{SHEETS}/{hoja_id}:batchUpdate", "ampliar la hoja de Google Sheets",
            json={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": propiedades["sheetId"], "gridProperties": nuevas},
                "fields": "gridProperties.rowCount,gridProperties.columnCount",
            }}]},
        )

    def escribir_valores(self, hoja_id, pestana, filas, lote=2000):
        """Escribe `filas` desde A1, en lotes para no exceder el tamaño de petición.

        RAW: los textos se guardan tal cual (p. ej. RUC con ceros a la izquierda).
        """
        if not filas:
            return
        self.asegurar_tamano(hoja_id, pestana, len(filas), max(len(f) for f in filas))
        for inicio in range(0, len(filas), lote):
            rango = quote(f"{_rango(pestana)}!A{inicio + 1}", safe="")
            self._pedir(
                "PUT", f"{SHEETS}/{hoja_id}/values/{rango}", "escribir en la hoja de Google Sheets",
                params={"valueInputOption": "RAW"},
                json={"values": filas[inicio:inicio + lote]},
            )


def _rango(pestana):
    return "'" + pestana.replace("'", "''") + "'"


def _detalle_error(respuesta):
    try:
        return respuesta.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return respuesta.text[:200]
