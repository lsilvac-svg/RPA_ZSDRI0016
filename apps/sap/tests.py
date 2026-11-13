from datetime import date

from django.test import SimpleTestCase, TestCase

from .forms import CredencialSAPForm
from .models import ConexionSAP, CredencialSAP
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


class CredencialSAPTests(TestCase):
    def setUp(self):
        self.conexion = ConexionSAP.objects.create(
            nombre="Prueba", conexion_logon="PRD_HANA", tiempo_espera=45
        )

    def test_clave_se_guarda_cifrada(self):
        credencial = CredencialSAP(conexion=self.conexion, usuario="RPA")
        credencial.clave = "Secreta#123"
        credencial.save()

        guardada = CredencialSAP.objects.get(pk=credencial.pk)
        self.assertNotIn("Secreta", guardada.clave_cifrada)
        self.assertEqual(guardada.clave, "Secreta#123")
        parametros = guardada.parametros()
        self.assertEqual(parametros.clave, "Secreta#123")
        self.assertEqual(parametros.usuario, "RPA")
        self.assertEqual(parametros.conexion_logon, "PRD_HANA")
        self.assertEqual(parametros.tiempo_espera, 45)

    def test_varios_logins_por_conexion(self):
        for usuario in ("RPA", "RPA_VENTAS"):
            credencial = CredencialSAP(conexion=self.conexion, usuario=usuario)
            credencial.clave = "x"
            credencial.save()
        self.assertEqual(self.conexion.credenciales.count(), 2)

    def test_formulario_exige_clave_y_normaliza_usuario(self):
        form = CredencialSAPForm(data={"conexion": self.conexion.pk, "usuario": " rpa2 ", "activa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("clave", form.errors)

        form = CredencialSAPForm(data={
            "conexion": self.conexion.pk, "usuario": " rpa2 ", "clave": "x", "activa": True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().usuario, "RPA2")
