from contextlib import contextmanager
from datetime import date, datetime, time
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.sap.models import ConexionSAP
from apps.sap.motor import ErrorSAP, SinDatos

from . import ejecutor, planificador, registro
from .base import Resultado, RobotSAP
from .models import Ejecucion, EstadoWorker, Programacion, Robot
from .parametros import Parametro, Tipo, construir_formulario, resolver, serializar


def local(*args):
    return timezone.make_aware(datetime(*args))


class PlanificadorTests(TestCase):
    def setUp(self):
        self.robot = Robot.objects.create(codigo="PRUEBA", nombre="Prueba")

    def _programacion(self, **campos):
        return Programacion(robot=self.robot, nombre="p", hora=time(6, 30), **campos)

    def test_diaria(self):
        p = self._programacion(frecuencia=Programacion.Frecuencia.DIARIA)
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 2, 7, 0)), local(2026, 11, 3, 6, 30))
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 2, 5, 0)), local(2026, 11, 2, 6, 30))

    def test_semanal(self):
        # 2026-11-02 es lunes; programado martes (1) y viernes (4)
        p = self._programacion(frecuencia=Programacion.Frecuencia.SEMANAL, dias_semana="1,4")
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 2, 12, 0)), local(2026, 11, 3, 6, 30))
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 3, 12, 0)), local(2026, 11, 6, 6, 30))

    def test_mensual_usa_ultimo_dia_si_el_mes_es_corto(self):
        p = self._programacion(frecuencia=Programacion.Frecuencia.MENSUAL, dia_mes=31)
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 2, 0, 0)), local(2026, 11, 30, 6, 30))
        p = self._programacion(frecuencia=Programacion.Frecuencia.MENSUAL, dia_mes=1)
        self.assertEqual(planificador.calcular_proxima(p, local(2026, 11, 2, 0, 0)), local(2026, 12, 1, 6, 30))

    def test_encola_vencidas_sin_duplicar(self):
        p = Programacion.objects.create(
            robot=self.robot, nombre="p", hora=time(6, 30),
            frecuencia=Programacion.Frecuencia.DIARIA,
        )
        Programacion.objects.filter(pk=p.pk).update(proxima_ejecucion=timezone.now())

        self.assertEqual(planificador.encolar_vencidas(), 1)
        Programacion.objects.filter(pk=p.pk).update(proxima_ejecucion=timezone.now())
        self.assertEqual(planificador.encolar_vencidas(), 0)  # ya hay una en cola

        p.refresh_from_db()
        self.assertGreater(p.proxima_ejecucion, timezone.now())
        self.assertEqual(Ejecucion.objects.filter(origen=Ejecucion.Origen.PROGRAMADA).count(), 1)


class EstadoWorkerTests(TestCase):
    def test_estados(self):
        worker = EstadoWorker.obtener()
        self.assertEqual(worker.estado, EstadoWorker.Estado.NO_INICIADO)

        worker.ultimo_latido = timezone.now()
        self.assertEqual(worker.estado, EstadoWorker.Estado.ACTIVO)
        self.assertTrue(worker.activo)

        worker.habilitado = False
        self.assertEqual(worker.estado, EstadoWorker.Estado.PAUSADO)
        self.assertFalse(worker.activo)

        worker.ultimo_latido = timezone.now() - EstadoWorker.LIMITE_LATIDO
        self.assertEqual(worker.estado, EstadoWorker.Estado.NO_INICIADO)


class ParametrosTests(TestCase):
    DEFINICION = (
        Parametro("carpeta", "Carpeta", Tipo.CARPETA, defecto=r"C:\Temp", requerido=True),
        Parametro("filas", "Filas", Tipo.ENTERO, defecto=5),
        Parametro("abrir", "Abrir", Tipo.BOOLEANO, defecto=True),
        Parametro("desde", "Desde", Tipo.FECHA),
    )

    def test_formulario_y_serializacion(self):
        form = construir_formulario(self.DEFINICION, data={
            "carpeta": r" Z:\Ventas ", "filas": "7", "desde": "2026-10-01",
        })
        self.assertTrue(form.is_valid(), form.errors)
        datos = serializar(self.DEFINICION, form.cleaned_data)
        self.assertEqual(datos, {"carpeta": r"Z:\Ventas", "filas": 7, "abrir": False, "desde": "2026-10-01"})
        self.assertEqual(resolver(self.DEFINICION, datos)["desde"], date(2026, 10, 1))

    def test_resolver_usa_valores_por_defecto(self):
        valores = resolver(self.DEFINICION, {"filas": None})
        self.assertEqual(valores, {"carpeta": r"C:\Temp", "filas": 5, "abrir": True, "desde": None})


class RobotFalso(RobotSAP):
    codigo = "FALSO"
    nombre = "Robot falso"
    parametros_ejecucion = (Parametro("modo", "Modo"),)

    def ejecutar(self, ctx):
        ctx.paso("Paso de prueba", lambda: None)
        modo = ctx.parametros["modo"]
        if modo == "sin_datos":
            raise SinDatos("No hay datos")
        if modo == "falla":
            raise ErrorSAP("SAP no responde")
        return Resultado(mensaje="Listo", archivo=r"C:\Temp\x.xlsx")


@contextmanager
def sap_simulado():
    """Reemplaza la conexión real a SAP por objetos simulados."""
    sesion = mock.MagicMock()
    sesion.barra_estado.return_value = ("S", "")
    conector = mock.MagicMock()
    conector.return_value.__enter__.return_value = sesion
    with mock.patch.object(ejecutor, "ConectorSAP", conector), \
            mock.patch.object(ejecutor, "VigilanteSeguridad", mock.MagicMock()), \
            mock.patch.object(ejecutor.time, "sleep"):
        yield sesion


class EjecutorTests(TestCase):
    def setUp(self):
        registro.registrar(RobotFalso)
        conexion = ConexionSAP(nombre="Prueba", conexion_logon="PRD", usuario="RPA")
        conexion.clave = "x"
        conexion.save()
        self.robot = Robot.objects.create(
            codigo="FALSO", nombre="Robot falso", conexion=conexion,
            reintentos=2, espera_entre_intentos=0,
        )

    def _ejecutar(self, modo):
        ejecucion = Ejecucion.objects.create(robot=self.robot, parametros={"modo": modo})
        with sap_simulado():
            ejecutor.ejecutar(ejecucion)
        ejecucion.refresh_from_db()
        return ejecucion

    def test_exitosa(self):
        ejecucion = self._ejecutar("ok")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.EXITOSA)
        self.assertEqual(ejecucion.archivo, r"C:\Temp\x.xlsx")
        self.assertTrue(ejecucion.logs.filter(mensaje="FIN: Paso de prueba").exists())

    def test_sin_datos_no_reintenta(self):
        ejecucion = self._ejecutar("sin_datos")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.SIN_DATOS)
        self.assertEqual(ejecucion.intentos, 1)

    def test_error_recuperable_reintenta_y_falla(self):
        ejecucion = self._ejecutar("falla")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertEqual(ejecucion.intentos, 2)
        self.assertIn("SAP no responde", ejecucion.mensaje)

    def test_cancelacion_solicitada(self):
        ejecucion = Ejecucion.objects.create(
            robot=self.robot, parametros={"modo": "ok"}, cancelacion_solicitada=True
        )
        with sap_simulado():
            ejecutor.ejecutar(ejecucion)
        ejecucion.refresh_from_db()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.CANCELADA)

    def test_sin_conexion_falla_sin_intentar(self):
        self.robot.conexion = None
        self.robot.save()
        ejecucion = self._ejecutar("ok")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertEqual(ejecucion.intentos, 0)


class VistasEjecucionTests(TestCase):
    def setUp(self):
        registro.registrar(RobotFalso)
        conexion = ConexionSAP(nombre="Prueba", conexion_logon="PRD", usuario="RPA")
        conexion.clave = "x"
        conexion.save()
        self.robot = Robot.objects.create(codigo="FALSO", nombre="Robot falso", conexion=conexion)
        self.usuario = Usuario.objects.create_user("usuario@ipesa.com.pe", "x")
        self.otro = Usuario.objects.create_user("otro@ipesa.com.pe", "x")

    def test_usuario_encola_ejecucion(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("robots:ejecutar", args=[self.robot.pk]), {"ej-modo": "ok"})
        ejecucion = Ejecucion.objects.get()
        self.assertRedirects(respuesta, reverse("robots:ejecucion", args=[ejecucion.pk]))
        self.assertEqual(ejecucion.parametros, {"modo": "ok"})
        self.assertEqual(ejecucion.solicitada_por, self.usuario)

    def test_usuario_no_cancela_ejecuciones_de_otro(self):
        ejecucion = Ejecucion.objects.create(robot=self.robot, solicitada_por=self.otro)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("robots:cancelar", args=[ejecucion.pk]))
        self.assertEqual(respuesta.status_code, 403)

    def test_cancelar_pendiente(self):
        ejecucion = Ejecucion.objects.create(robot=self.robot, solicitada_por=self.usuario)
        self.client.force_login(self.usuario)
        self.client.post(reverse("robots:cancelar", args=[ejecucion.pk]))
        ejecucion.refresh_from_db()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.CANCELADA)

    def test_usuario_no_puede_pausar_worker(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("robots:worker_cambiar"), {"accion": "pausar"})
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(EstadoWorker.obtener().habilitado)

    def test_admin_pausa_y_activa_worker(self):
        admin = Usuario.objects.create_user("admin@ipesa.com.pe", "x", rol=Usuario.Rol.ADMIN)
        self.client.force_login(admin)

        self.client.post(reverse("robots:worker_cambiar"), {"accion": "pausar"})
        worker = EstadoWorker.obtener()
        self.assertFalse(worker.habilitado)
        self.assertEqual(worker.cambiado_por, admin)

        self.client.post(reverse("robots:worker_cambiar"), {"accion": "activar"})
        self.assertTrue(EstadoWorker.obtener().habilitado)

    def test_monitor_parcial_htmx(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("robots:monitor"), headers={"HX-Request": "true"})
        self.assertContains(respuesta, 'id="monitor"')
        self.assertNotContains(respuesta, "<html")
