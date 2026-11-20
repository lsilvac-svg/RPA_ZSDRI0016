from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from apps.robots import registro
from apps.robots.base import ContextoEjecucion
from apps.robots.parametros import resolver
from apps.sap.motor import SinDatos

from . import robot as modulo
from .robot import RobotFbl1nAnticipos


def contexto(sesion, **config):
    valores = resolver(RobotFbl1nAnticipos.parametros_config, config)
    return ContextoEjecucion(
        sesion=sesion, config=valores, parametros={"fecha_clave": date(2026, 11, 12)},
        log=mock.MagicMock(), cancelacion_solicitada=lambda: False,
    )


class RobotFbl1nAnticiposTests(SimpleTestCase):
    def setUp(self):
        self.sesion = mock.MagicMock()
        self.sesion.barra_estado.return_value = ("S", "")
        self.sesion.leer.return_value = "export.XLSX"
        self.sesion.tiempo_espera = 1

    def test_esta_registrado(self):
        self.assertIs(registro.obtener("FBL1N_ANTICIPOS"), RobotFbl1nAnticipos)

    def test_configuracion_por_defecto(self):
        config = resolver(RobotFbl1nAnticipos.parametros_config, {})
        self.assertEqual(config["carpeta_exportacion"], r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP")
        self.assertEqual(config["sociedad"], "PE01")
        self.assertEqual(config["variante"], "/CXP EDWIN")

    def test_usa_variante_por_defecto(self):
        self.sesion.existe.side_effect = lambda id_: (
            id_ == modulo.CAMPO_SOCIEDAD and not self.sesion.tecla.called
        )
        with mock.patch.object(modulo.alv, "exportar_excel", return_value="Y:/x.xlsx"), \
                mock.patch.object(modulo.archivos, "cerrar_excel"):
            RobotFbl1nAnticipos().ejecutar(contexto(self.sesion))
        self.sesion.escribir.assert_any_call(modulo.CAMPO_VARIANTE, "/CXP EDWIN")

    def test_flujo_completo_con_variante_por_nombre(self):
        # Tras abrir la FBL1N existe la pantalla de selección; tras F8, el listado
        self.sesion.existe.side_effect = lambda id_: {
            modulo.CAMPO_SOCIEDAD: not self.sesion.tecla.called,
        }.get(id_, False)

        with mock.patch.object(modulo.alv, "exportar_excel", return_value="Y:/x.xlsx") as exportar, \
                mock.patch.object(modulo.archivos, "cerrar_excel"):
            resultado = RobotFbl1nAnticipos().ejecutar(contexto(self.sesion, variante="/ANTICIPOS"))

        self.sesion.comando.assert_called_with("/nFBL1N")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_SOCIEDAD, "PE01")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_FECHA_CLAVE, "12.11.2026")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_VARIANTE, "/ANTICIPOS")
        self.assertEqual(self.sesion.elemento(modulo.COMBO_FORMATO).key, "xlsx-TT")
        self.assertEqual(exportar.call_args.args[3], "Anticipos_FBL1N_2026")  # nombre fijo
        self.assertIn("Y:/x.xlsx", resultado.mensaje)

    def test_fecha_en_nombre_opcional(self):
        self.sesion.existe.side_effect = lambda id_: (
            id_ == modulo.CAMPO_SOCIEDAD and not self.sesion.tecla.called
        )
        with mock.patch.object(modulo.alv, "exportar_excel", return_value="Y:/x.xlsx") as exportar, \
                mock.patch.object(modulo.archivos, "cerrar_excel"):
            RobotFbl1nAnticipos().ejecutar(
                contexto(self.sesion, variante="/ANTICIPOS", fecha_en_nombre=True)
            )
        self.assertEqual(exportar.call_args.args[3], "Anticipos_FBL1N_2026_20261112")

    def test_sin_partidas(self):
        self.sesion.existe.side_effect = lambda id_: id_ == modulo.CAMPO_SOCIEDAD
        self.sesion.barra_estado.return_value = ("S", "No se ha seleccionado ninguna partida")
        with self.assertRaises(SinDatos):
            RobotFbl1nAnticipos().ejecutar(contexto(self.sesion, variante="/ANTICIPOS"))
