from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from apps.robots import registro
from apps.robots.base import ContextoEjecucion
from apps.robots.parametros import resolver
from apps.sap.motor import ErrorFatal, ErrorSAP, SinDatos

from . import robot as modulo
from .robot import RobotFbl5nClientes


def contexto(sesion, **config):
    valores = resolver(RobotFbl5nClientes.parametros_config, config)
    return ContextoEjecucion(
        sesion=sesion, config=valores, parametros={"fecha_clave": date(2026, 11, 20)},
        log=mock.MagicMock(), cancelacion_solicitada=lambda: False,
    )


class RobotFbl5nClientesTests(SimpleTestCase):
    def setUp(self):
        self.sesion = mock.MagicMock()
        self.sesion.barra_estado.return_value = ("S", "")
        self.sesion.leer.return_value = "export.XLSX"
        self.sesion.tiempo_espera = 1
        # Pantalla de selección hasta pulsar F8; luego el listado
        self.sesion.existe.side_effect = lambda id_: (
            id_ == modulo.CAMPO_SOCIEDAD and not self._f8_pulsado()
        )

    def _f8_pulsado(self):
        return mock.call(8) in self.sesion.tecla.call_args_list

    def _ejecutar(self, **config):
        with mock.patch.object(modulo.alv, "exportar_excel", return_value="Y:/x.xlsx") as exportar, \
                mock.patch.object(modulo.archivos, "cerrar_excel") as cerrar:
            resultado = RobotFbl5nClientes().ejecutar(contexto(self.sesion, **config))
        return resultado, exportar, cerrar

    def test_esta_registrado(self):
        self.assertIs(registro.obtener("FBL5N_CLIENTES"), RobotFbl5nClientes)

    def test_configuracion_por_defecto(self):
        config = resolver(RobotFbl5nClientes.parametros_config, {})
        self.assertEqual(config["carpeta_exportacion"],
                         r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP")
        self.assertEqual(config["nombre_reporte"], "Archivo_FBL5N")
        self.assertEqual(config["sociedad"], "PE01")
        self.assertEqual(config["variante"], "/CXC EDWIN")

    def test_usa_variante_por_defecto(self):
        self._ejecutar()
        self.sesion.escribir.assert_any_call(modulo.CAMPO_VARIANTE, "/CXC EDWIN")

    def test_flujo_completo_con_variante_por_nombre(self):
        resultado, exportar, cerrar = self._ejecutar(variante="/CXC")

        self.sesion.comando.assert_called_with("/nFBL5N")
        self.assertTrue(self.sesion.elemento(modulo.CHECK_OPERACIONES_CME).selected)
        self.assertTrue(self.sesion.elemento(modulo.CHECK_PARTIDAS_MEMO).selected)
        self.sesion.escribir.assert_any_call(modulo.CAMPO_SOCIEDAD, "PE01")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_FECHA_CLAVE, "20.11.2026")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_VARIANTE, "/CXC")
        self.sesion.seleccionar_menu.assert_called_with(modulo.MENU_EXPORTAR)
        self.assertEqual(self.sesion.elemento(modulo.COMBO_FORMATO).key, "xlsx-TT")
        self.assertEqual(exportar.call_args.args[2],
                         r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\REPORTE_SAP")
        self.assertEqual(exportar.call_args.args[3], "Archivo_FBL5N")  # nombre fijo
        cerrar.assert_called_once()
        self.assertIn("Y:/x.xlsx", resultado.mensaje)

    def test_no_cierra_excel_si_no_se_abre(self):
        _, _, cerrar = self._ejecutar(variante="/CXC", abrir_excel=False)
        cerrar.assert_not_called()

    def test_sin_partidas(self):
        self.sesion.existe.side_effect = lambda id_: id_ == modulo.CAMPO_SOCIEDAD
        self.sesion.barra_estado.return_value = ("S", "No se ha seleccionado ninguna partida")
        with self.assertRaises(SinDatos):
            self._ejecutar(variante="/CXC")

    def test_error_sap_tras_ejecutar(self):
        self.sesion.existe.side_effect = lambda id_: id_ == modulo.CAMPO_SOCIEDAD
        self.sesion.barra_estado.return_value = ("E", "La variante /XX no existe")
        with self.assertRaises(ErrorSAP):
            self._ejecutar(variante="/XX")

    def test_transaccion_no_disponible(self):
        self.sesion.existe.side_effect = lambda id_: False
        self.sesion.barra_estado.return_value = ("E", "Sin autorización para FBL5N")
        with self.assertRaises(ErrorFatal):
            self._ejecutar(variante="/CXC")
