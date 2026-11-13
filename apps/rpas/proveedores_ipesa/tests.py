from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from apps.robots import registro
from apps.robots.base import ContextoEjecucion
from apps.robots.parametros import resolver
from apps.sap.motor import ErrorFatal, SinDatos

from . import robot as modulo
from .robot import RobotProveedoresIpesa

PERIODO = {"fecha_desde": date(2026, 10, 1), "fecha_hasta": date(2026, 10, 31)}


def contexto(sesion, **config):
    valores = resolver(RobotProveedoresIpesa.parametros_config, config)
    return ContextoEjecucion(
        sesion=sesion, config=valores, parametros=PERIODO,
        log=mock.MagicMock(), cancelacion_solicitada=lambda: False,
    )


class RobotProveedoresIpesaTests(SimpleTestCase):
    def setUp(self):
        self.sesion = mock.MagicMock()
        self.sesion.barra_estado.return_value = ("S", "")
        self.sesion.tiempo_espera = 1
        self.campo = self.sesion.elemento("wnd[0]").GuiFocus
        self.campo.Id = "/app/con[0]/ses[0]/wnd[0]/usr/ctxtS_EKORG-LOW"
        # Antes de F8 se está en la pantalla de selección; después, en el listado
        self.sesion.existe.side_effect = lambda id_: (
            id_ == modulo.CAMPO_FECHA_DESDE
            and mock.call(8) not in self.sesion.tecla.call_args_list
        )

    def _ejecutar(self, **config):
        with mock.patch.object(modulo.alv, "exportar_excel", return_value="Y:/x.xlsx") as exportar, \
                mock.patch.object(modulo.archivos, "cerrar_excel"):
            resultado = RobotProveedoresIpesa().ejecutar(contexto(self.sesion, **config))
        return resultado, exportar

    def test_esta_registrado(self):
        self.assertIs(registro.obtener("PROVEEDORES_IPESA"), RobotProveedoresIpesa)

    def test_configuracion_por_defecto(self):
        config = resolver(RobotProveedoresIpesa.parametros_config, {})
        self.assertEqual(
            config["carpeta_exportacion"], r"Y:\2026\CUENTAS POR PAGAR 2026\MASIVO\LISTA_PROVEEDORES"
        )

    def test_flujo_con_lista_f4_como_la_grabacion(self):
        resultado, exportar = self._ejecutar()
        self.sesion.comando.assert_called_with("/nZMMRI0017")
        self.sesion.tecla.assert_any_call(4)
        self.sesion.com.findById.assert_any_call("wnd[1]/usr/lbl[1,4]", False)
        self.sesion.presionar.assert_any_call(modulo.BOTON_ACEPTAR_F4)
        self.sesion.escribir.assert_any_call(modulo.CAMPO_FECHA_DESDE, "01.10.2026")
        self.sesion.escribir.assert_any_call(modulo.CAMPO_FECHA_HASTA, "31.10.2026")
        self.assertEqual(exportar.call_args.args[3], "Proveedores_Ipesa_202610")
        self.assertIn("Y:/x.xlsx", resultado.mensaje)

    def test_valor_del_primer_campo_configurado(self):
        self._ejecutar(valor_campo_inicial="PE01")
        self.assertEqual(self.campo.text, "PE01")
        self.assertNotIn(mock.call(4), self.sesion.tecla.call_args_list)

    def test_sin_resultados(self):
        self.sesion.existe.side_effect = lambda id_: id_ == modulo.CAMPO_FECHA_DESDE
        with self.assertRaises(SinDatos):
            self._ejecutar(valor_campo_inicial="PE01")

    def test_periodo_invertido_es_error(self):
        with self.assertRaises(ErrorFatal):
            RobotProveedoresIpesa._periodo({
                "fecha_desde": date(2026, 10, 31), "fecha_hasta": date(2026, 10, 1),
            })
