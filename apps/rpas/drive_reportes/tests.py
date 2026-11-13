import os
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase
from openpyxl import Workbook

from apps.integraciones.models import CuentaGoogle
from apps.integraciones.tests import CLAVE
from apps.robots import ejecutor, registro
from apps.robots.models import Ejecucion, Robot

from . import robot as modulo
from .robot import RobotDriveReportes


def crear_excel(ruta, filas):
    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    libro.save(ruta)


class RobotDriveReportesTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.proveedores = base / "LISTA_PROVEEDORES"
        self.reporte = base / "REPORTE_SAP"
        self.proveedores.mkdir()
        self.reporte.mkdir()

        cabecera = ["Organización compras", "Proveedor", "Nombre 1", "Sector"]
        crear_excel(self.proveedores / "Proveedores_Ipesa_202610.xlsx", [cabecera, ["PE01", "1", "VIEJO", "A"]])
        reciente = self.proveedores / "Proveedores_Ipesa_202611.xlsx"
        crear_excel(reciente, [cabecera, ["PE01", "1", "ACME", "A"], ["PE01", "1", "ACME", "B"]])
        futuro = time.time() + 60
        os.utime(reciente, (futuro, futuro))
        crear_excel(self.reporte / "Anticipos_FBL1N_20261112.xlsx", [["Cuenta"], ["20000005"]])

        cuenta = CuentaGoogle(nombre="RPA")
        cuenta.clave = CLAVE
        cuenta.save()

        self.robot = Robot.objects.create(
            codigo="DRIVE_REPORTES", nombre="Drive", reintentos=1, espera_entre_intentos=0,
            configuracion={
                "carpeta_proveedores": str(self.proveedores),
                "carpeta_reporte_sap": str(self.reporte),
                "hoja_proveedores": "https://docs.google.com/spreadsheets/d/HOJA1/edit",
                "carpeta_drive_reporte": "https://drive.google.com/drive/folders/CARPETA1",
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _ejecutar(self):
        cliente = mock.MagicMock()
        cliente.leer_valores.return_value = []
        cliente.reemplazar_archivo.return_value = ({"webViewLink": "https://x"}, False)
        ejecucion = Ejecucion.objects.create(robot=self.robot)
        with mock.patch.object(modulo, "ClienteGoogle", return_value=cliente), \
                mock.patch.object(ejecutor, "ConectorSAP") as conector:
            ejecutor.ejecutar(ejecucion)
        ejecucion.refresh_from_db()
        return ejecucion, cliente, conector

    def test_esta_registrado_y_no_usa_sap(self):
        self.assertIs(registro.obtener("DRIVE_REPORTES"), RobotDriveReportes)
        self.assertFalse(self.robot.requiere_sap)

    def test_sube_ambos_sin_abrir_sap_ni_login(self):
        ejecucion, cliente, conector = self._ejecutar()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.EXITOSA, ejecucion.mensaje)
        conector.assert_not_called()

        # Proveedores: el archivo más reciente, fusionado en la hoja
        hoja, pestana, filas = cliente.escribir_valores.call_args.args
        self.assertEqual((hoja, pestana), ("HOJA1", "Proveedores"))
        self.assertEqual([f[2] for f in filas[1:]], ["ACME", "ACME"])
        self.assertIn("2 nuevos", ejecucion.mensaje)

        # Reporte SAP: reemplazo con nombre fijo
        carpeta, nombre, contenido = cliente.reemplazar_archivo.call_args.args
        self.assertEqual((carpeta, nombre), ("CARPETA1", "Anticipos_FBL1N.xlsx"))
        self.assertTrue(contenido.startswith(b"PK"))

    def test_sin_archivo_de_proveedores_igual_sube_el_reporte(self):
        for archivo in self.proveedores.iterdir():
            archivo.unlink()
        ejecucion, cliente, _ = self._ejecutar()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.EXITOSA)
        cliente.escribir_valores.assert_not_called()
        cliente.reemplazar_archivo.assert_called_once()
        self.assertIn("No hay archivos", ejecucion.mensaje)

    def test_falta_hoja_configurada(self):
        self.robot.configuracion["hoja_proveedores"] = ""
        self.robot.save()
        ejecucion, cliente, _ = self._ejecutar()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertIn("hoja de Google Sheets", ejecucion.mensaje)
        self.assertIn("Reporte SAP reemplazado", ejecucion.mensaje)  # la otra parte sí se hizo
        cliente.reemplazar_archivo.assert_called_once()

    def test_mensaje_incluye_todos_los_errores(self):
        self.robot.configuracion["hoja_proveedores"] = ""
        self.robot.save()
        cliente = mock.MagicMock()
        cliente.reemplazar_archivo.side_effect = modulo.ErrorFatal("sin espacio")
        ejecucion = Ejecucion.objects.create(robot=self.robot)
        with mock.patch.object(modulo, "ClienteGoogle", return_value=cliente):
            ejecutor.ejecutar(ejecucion)
        ejecucion.refresh_from_db()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertIn("Proveedores: Falta la hoja", ejecucion.mensaje)
        self.assertIn("Reporte SAP: sin espacio", ejecucion.mensaje)
