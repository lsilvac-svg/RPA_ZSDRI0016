import json
from datetime import datetime
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.cuentas.models import Usuario
from apps.sap.motor import ErrorFatal, ErrorSAP

from .forms import CuentaGoogleForm
from .google_api import ClienteGoogle, extraer_id
from .models import CuentaGoogle, validar_clave_json
from .tablas import COLUMNA_ACTUALIZACION, fusionar, valor_celda

CLAVE = json.dumps({
    "type": "service_account",
    "client_email": "rpa-drive@proyecto.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
})
CABECERA = ["Organización compras", "Proveedor", "Nombre 1", "Sector", "Proveedor"]
CLAVES = ["Organización compras", "Proveedor", "Sector"]


class FusionTests(SimpleTestCase):
    def test_hoja_vacia_escribe_todo(self):
        filas = [["PE01", "100", "ACME", "A", "X"], ["PE01", "100", "ACME", "B", "X"]]
        r = fusionar([], CABECERA, filas, CLAVES, "2026-11-12 10:00")
        self.assertEqual(r.nuevas, 2)
        self.assertEqual(r.filas[0], CABECERA + [COLUMNA_ACTUALIZACION])
        self.assertEqual(r.filas[1][-1], "2026-11-12 10:00")

    def test_actualiza_agrega_y_conserva_historicos(self):
        existentes = [
            CABECERA + [COLUMNA_ACTUALIZACION],
            ["PE01", 100, "ACME", "A", "X", "2026-11-01 08:00"],   # cambia nombre
            ["PE01", 200, "BETA", "A", "X", "2026-11-01 08:00"],   # igual
            ["PE01", 300, "VIEJO", "A", "X", "2026-10-01 08:00"],  # ya no viene
        ]
        nuevas = [
            ["PE01", "100", "ACME SAC", "A", "X"],
            ["PE01", "200", "BETA", "A", "X"],
            ["PE01", "400", "NUEVO", "A", "X"],
        ]
        r = fusionar(existentes, CABECERA, nuevas, CLAVES, "2026-11-12 10:00")
        self.assertEqual((r.nuevas, r.actualizadas, r.sin_cambios, r.conservadas), (1, 1, 1, 1))
        self.assertEqual(len(r.filas), 5)
        self.assertEqual(r.filas[1][2], "ACME SAC")
        self.assertEqual(r.filas[1][-1], "2026-11-12 10:00")
        self.assertEqual(r.filas[2][-1], "2026-11-01 08:00")  # sin cambios: conserva fecha
        self.assertEqual(r.filas[3][2], "VIEJO")
        self.assertEqual(r.filas[4][1], "400")

    def test_columna_nueva_en_el_excel(self):
        existentes = [["Organización compras", "Proveedor", "Sector", COLUMNA_ACTUALIZACION],
                      ["PE01", "1", "A", "x"]]
        r = fusionar(existentes, ["Organización compras", "Proveedor", "Sector", "RUC"],
                     [["PE01", "1", "A", "2010"]], CLAVES, "t")
        self.assertEqual(r.columnas_nuevas, ["RUC"])
        self.assertEqual(r.filas[0][-2:], ["RUC", COLUMNA_ACTUALIZACION])
        self.assertEqual(r.filas[1], ["PE01", "1", "A", "2010", "t"])

    def test_falta_columna_clave(self):
        with self.assertRaises(ValueError):
            fusionar([], ["Proveedor"], [["1"]], CLAVES, "t")

    def test_valor_celda(self):
        self.assertEqual(valor_celda(datetime(2026, 1, 5)), "2026-01-05")
        self.assertEqual(valor_celda(3.0), 3)
        self.assertEqual(valor_celda(None), "")
        self.assertEqual(valor_celda(" 08774207 "), "08774207")


class ClaveTests(SimpleTestCase):
    def test_valida_cuenta_de_servicio(self):
        self.assertEqual(validar_clave_json(CLAVE)["client_email"], "rpa-drive@proyecto.iam.gserviceaccount.com")
        with self.assertRaises(ValidationError):
            validar_clave_json("{no es json")
        with self.assertRaises(ValidationError):
            validar_clave_json(json.dumps({"type": "authorized_user"}))

    def test_extraer_id(self):
        self.assertEqual(extraer_id("https://docs.google.com/spreadsheets/d/1AbC_x-9/edit#gid=0"), "1AbC_x-9")
        self.assertEqual(extraer_id("https://drive.google.com/drive/folders/0FoLd3r?usp=sharing"), "0FoLd3r")
        self.assertEqual(extraer_id(" 1AbC "), "1AbC")


class ClienteGoogleTests(SimpleTestCase):
    def _cliente(self, estado, cuerpo):
        respuesta = mock.MagicMock(status_code=estado, content=b"x", text=json.dumps(cuerpo))
        respuesta.json.return_value = cuerpo
        http = mock.MagicMock()
        http.request.return_value = respuesta
        return ClienteGoogle({"client_email": "rpa@x"}, sesion_http=http)

    def test_sin_permiso_es_error_fatal_con_el_correo(self):
        cliente = self._cliente(404, {"error": {"message": "File not found"}})
        with self.assertRaisesRegex(ErrorFatal, "rpa@x"):
            cliente.leer_valores("ID", "Proveedores")

    def test_error_temporal_se_reintenta(self):
        cliente = self._cliente(503, {"error": {"message": "Backend Error"}})
        with self.assertRaises(ErrorSAP):
            cliente.leer_valores("ID", "Proveedores")

    def test_amplia_la_hoja_antes_de_escribir(self):
        cliente = self._cliente(200, {"sheets": [{"properties": {
            "sheetId": 7, "title": "Proveedores",
            "gridProperties": {"rowCount": 1000, "columnCount": 26},
        }}]})
        filas = [["x"] * 37] * 4123
        cliente.escribir_valores("ID", "Proveedores", filas)

        llamadas = cliente.http.request.call_args_list
        ampliar = llamadas[1]
        propiedades = ampliar.kwargs["json"]["requests"][0]["updateSheetProperties"]["properties"]
        self.assertEqual(propiedades["gridProperties"], {"rowCount": 4123, "columnCount": 37})
        self.assertEqual(propiedades["sheetId"], 7)
        escrituras = [c for c in llamadas if c.args[0] == "PUT"]
        self.assertEqual(len(escrituras), 3)  # lotes de 2000: A1, A2001, A4001
        self.assertIn("A4001", escrituras[-1].args[1])

    def test_cuota_de_cuenta_de_servicio(self):
        cliente = self._cliente(403, {"error": {"message": "storageQuotaExceeded"}})
        with self.assertRaisesRegex(ErrorFatal, "Unidad compartida"):
            cliente.verificar_carpeta("ID")


class CuentaGoogleTests(TestCase):
    def test_formulario_guarda_clave_cifrada(self):
        form = CuentaGoogleForm(
            data={"nombre": "RPA", "activa": True},
            files={"archivo_clave": SimpleUploadedFile("clave.json", CLAVE.encode())},
        )
        self.assertTrue(form.is_valid(), form.errors)
        cuenta = form.save()
        self.assertEqual(cuenta.correo, "rpa-drive@proyecto.iam.gserviceaccount.com")
        self.assertNotIn("PRIVATE", cuenta.clave_cifrada)
        self.assertEqual(cuenta.info_clave()["type"], "service_account")

    def test_formulario_exige_clave_al_crear(self):
        form = CuentaGoogleForm(data={"nombre": "RPA", "activa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("archivo_clave", form.errors)

    def test_elegir(self):
        with self.assertRaises(LookupError):
            CuentaGoogle.elegir()
        cuenta = CuentaGoogle(nombre="RPA")
        cuenta.clave = CLAVE
        cuenta.save()
        self.assertEqual(CuentaGoogle.elegir(), cuenta)
        with self.assertRaises(LookupError):
            CuentaGoogle.elegir("Otra")

    def test_solo_admin_ve_la_pantalla(self):
        usuario = Usuario.objects.create_user("usuario@ipesa.com.pe", "x")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("integraciones:lista")).status_code, 403)
