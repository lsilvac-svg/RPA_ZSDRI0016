from datetime import date

from django.test import SimpleTestCase, TestCase

from .models import ConexionSAP
from .motor import fechas


class FechasTests(SimpleTestCase):
    def test_mes_anterior(self):
        self.assertEqual(fechas.mes_anterior(date(2027, 1, 15)), (date(2026, 12, 1), date(2026, 12, 31)))
        self.assertEqual(fechas.mes_anterior(date(2028, 3, 1)), (date(2028, 2, 1), date(2028, 2, 29)))

    def test_sufijo_periodo(self):
        self.assertEqual(fechas.sufijo_periodo(date(2026, 10, 1), date(2026, 10, 31)), "202610")
        self.assertEqual(
            fechas.sufijo_periodo(date(2026, 10, 5), date(2026, 10, 20)), "20261005-20261020"
        )
        self.assertEqual(
            fechas.sufijo_periodo(date(2026, 9, 1), date(2026, 10, 31)), "20260901-20261031"
        )

    def test_formato_sap(self):
        self.assertEqual(fechas.a_sap(date(2026, 10, 1)), "01.10.2026")


class ConexionSAPTests(TestCase):
    def test_clave_se_guarda_cifrada(self):
        conexion = ConexionSAP(nombre="Prueba", conexion_logon="PRD_HANA", usuario="RPA")
        conexion.clave = "Secreta#123"
        conexion.save()

        guardada = ConexionSAP.objects.get(pk=conexion.pk)
        self.assertNotIn("Secreta", guardada.clave_cifrada)
        self.assertEqual(guardada.clave, "Secreta#123")
        self.assertEqual(guardada.parametros().clave, "Secreta#123")
