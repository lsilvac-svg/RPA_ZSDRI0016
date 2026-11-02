from datetime import date

from django.test import SimpleTestCase

from apps.robots import registro
from apps.sap.motor import ErrorFatal

from .robot import RobotZSDRI0016


class RobotZSDRI0016Tests(SimpleTestCase):
    def test_esta_registrado(self):
        self.assertIs(registro.obtener("ZSDRI0016"), RobotZSDRI0016)

    def test_periodo_por_defecto_es_mes_anterior(self):
        desde, hasta = RobotZSDRI0016._periodo({})
        self.assertEqual(desde.day, 1)
        self.assertLess(hasta, date.today().replace(day=1))

    def test_periodo_invertido_es_error(self):
        with self.assertRaises(ErrorFatal):
            RobotZSDRI0016._periodo({
                "fecha_desde": date(2026, 10, 31), "fecha_hasta": date(2026, 10, 1),
            })
