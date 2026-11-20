from datetime import date

from django.test import SimpleTestCase

from apps.robots import registro
from apps.robots.parametros import resolver
from apps.sap.motor import ErrorFatal

from .robot import MES_EN_CURSO, RobotZSDRI0016

CONFIG = {"nombre_reporte": "Reporte_ZSDRI0016"}


class RobotZSDRI0016Tests(SimpleTestCase):
    def test_esta_registrado(self):
        self.assertIs(registro.obtener("ZSDRI0016"), RobotZSDRI0016)

    def test_periodo_por_defecto_es_mes_anterior(self):
        parametros = resolver(RobotZSDRI0016.parametros_ejecucion, {})
        desde, hasta = RobotZSDRI0016._periodo(parametros, hoy=date(2026, 11, 20))
        self.assertEqual((desde, hasta), (date(2026, 10, 1), date(2026, 10, 31)))

    def test_periodo_mes_en_curso(self):
        desde, hasta = RobotZSDRI0016._periodo({"periodo": MES_EN_CURSO}, hoy=date(2026, 11, 20))
        self.assertEqual((desde, hasta), (date(2026, 11, 1), date(2026, 11, 20)))

    def test_fechas_explicitas_reemplazan_el_periodo(self):
        desde, hasta = RobotZSDRI0016._periodo(
            {"periodo": MES_EN_CURSO, "fecha_desde": date(2026, 11, 5)}, hoy=date(2026, 11, 20)
        )
        self.assertEqual((desde, hasta), (date(2026, 11, 5), date(2026, 11, 20)))

    def test_periodo_invertido_es_error(self):
        with self.assertRaises(ErrorFatal):
            RobotZSDRI0016._periodo({
                "fecha_desde": date(2026, 10, 31), "fecha_hasta": date(2026, 10, 1),
            })

    def test_nombre_con_periodo_por_defecto(self):
        nombre = RobotZSDRI0016._nombre_archivo(
            CONFIG, {}, date(2026, 11, 1), date(2026, 11, 20)
        )
        self.assertEqual(nombre, "Reporte_ZSDRI0016_20261101-20261120")

    def test_nombre_fijo(self):
        nombre = RobotZSDRI0016._nombre_archivo(
            CONFIG, {"nombre_archivo": " Ventas_Mes_Actual.xlsx "},
            date(2026, 11, 1), date(2026, 11, 20),
        )
        self.assertEqual(nombre, "Ventas_Mes_Actual")

    def test_nombre_fijo_invalido(self):
        with self.assertRaises(ErrorFatal):
            RobotZSDRI0016._nombre_archivo(
                CONFIG, {"nombre_archivo": "Ventas/Mes"}, date(2026, 11, 1), date(2026, 11, 20)
            )
