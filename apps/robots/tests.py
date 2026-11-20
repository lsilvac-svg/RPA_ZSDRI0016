from contextlib import contextmanager
from datetime import date, datetime, time
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.sap.models import ConexionSAP, CredencialSAP
from apps.sap.motor import ErrorSAP, SinDatos

from . import ejecutor, orquestacion, planificador, registro
from .base import Resultado, RobotSAP
from .models import (
    Ejecucion, EjecucionOrquestador, EstadoWorker, Orquestador, PasoOrquestador,
    Programacion, Robot,
)
from .parametros import Parametro, Tipo, construir_formulario, resolver, serializar


def crear_credencial(usuario="RPA", conexion=None):
    if conexion is None:
        conexion = ConexionSAP.objects.create(nombre="Prueba", conexion_logon="PRD")
    credencial = CredencialSAP(conexion=conexion, usuario=usuario)
    credencial.clave = "x"
    credencial.save()
    return credencial


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
        self.robot = Robot.objects.create(
            codigo="FALSO", nombre="Robot falso", credencial=crear_credencial(),
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
        self.robot.credencial = None
        self.robot.save()
        ejecucion = self._ejecutar("ok")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertEqual(ejecucion.intentos, 0)

    def test_login_inactivo_falla_sin_intentar(self):
        CredencialSAP.objects.update(activa=False)
        self.robot.refresh_from_db()
        ejecucion = self._ejecutar("ok")
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.FALLIDA)
        self.assertEqual(ejecucion.intentos, 0)
        self.assertIn("inactivo", ejecucion.mensaje)

    def test_cada_robot_entra_con_su_login(self):
        otro = crear_credencial("RPA_VENTAS", self.robot.credencial.conexion)
        self.robot.credencial = otro
        self.robot.save()
        ejecucion = Ejecucion.objects.create(robot=self.robot, parametros={"modo": "ok"})
        with sap_simulado() as sesion, mock.patch.object(ejecutor, "ConectorSAP") as conector:
            conector.return_value.__enter__.return_value = sesion
            ejecutor.ejecutar(ejecucion)
        ejecucion.refresh_from_db()
        self.assertEqual(ejecucion.estado, Ejecucion.Estado.EXITOSA)
        parametros = conector.call_args.args[0]
        self.assertEqual(parametros.usuario, "RPA_VENTAS")
        self.assertEqual(parametros.conexion_logon, "PRD")


class VistasEjecucionTests(TestCase):
    def setUp(self):
        registro.registrar(RobotFalso)
        self.robot = Robot.objects.create(
            codigo="FALSO", nombre="Robot falso", credencial=crear_credencial()
        )
        self.usuario = Usuario.objects.create_user("usuario@ipesa.com.pe", "x")
        self.otro = Usuario.objects.create_user("otro@ipesa.com.pe", "x")

    def test_usuario_encola_ejecucion(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("robots:ejecutar", args=[self.robot.pk]), {"ej-modo": "ok"})
        ejecucion = Ejecucion.objects.get()
        self.assertRedirects(respuesta, reverse("robots:ejecucion", args=[ejecucion.pk]))
        self.assertEqual(ejecucion.parametros, {"modo": "ok"})
        self.assertEqual(ejecucion.solicitada_por, self.usuario)

    def test_no_encola_si_el_robot_ya_esta_en_cola(self):
        Ejecucion.objects.create(robot=self.robot)
        self.client.force_login(self.usuario)
        self.client.post(reverse("robots:ejecutar", args=[self.robot.pk]), {"ej-modo": "ok"})
        self.assertEqual(Ejecucion.objects.count(), 1)

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


class OrquestacionTests(TestCase):
    def setUp(self):
        registro.registrar(RobotFalso)
        credencial = crear_credencial()
        self.robot_a = Robot.objects.create(codigo="FALSO", nombre="A", credencial=credencial,
                                            reintentos=1, espera_entre_intentos=0)
        self.orquestador = Orquestador.objects.create(nombre="Cierre")
        self.paso1 = PasoOrquestador.objects.create(
            orquestador=self.orquestador, orden=1, robot=self.robot_a, parametros={"modo": "ok"}
        )
        self.paso2 = PasoOrquestador.objects.create(
            orquestador=self.orquestador, orden=2, robot=self.robot_a, parametros={"modo": "x"}
        )

    def _terminar(self, ejecucion, estado):
        Ejecucion.objects.filter(pk=ejecucion.pk).update(estado=estado)
        ejecucion.refresh_from_db()
        orquestacion.avanzar(ejecucion)

    def test_iniciar_encola_solo_el_primer_paso(self):
        cadena = orquestacion.iniciar(self.orquestador)
        ejecucion = cadena.pasos.get()
        self.assertEqual(ejecucion.paso, self.paso1)
        self.assertEqual(ejecucion.parametros, {"modo": "ok"})

    def test_avanza_si_es_exitosa_y_cierra_al_final(self):
        cadena = orquestacion.iniciar(self.orquestador)
        self._terminar(cadena.pasos.get(), Ejecucion.Estado.EXITOSA)
        segunda = cadena.pasos.get(paso=self.paso2)
        self.assertEqual(segunda.estado, Ejecucion.Estado.PENDIENTE)
        self.assertEqual(segunda.parametros, {"modo": "x"})

        self._terminar(segunda, Ejecucion.Estado.EXITOSA)
        cadena.refresh_from_db()
        self.assertEqual(cadena.estado, EjecucionOrquestador.Estado.EXITOSA)

    def test_se_detiene_si_falla_o_se_cancela(self):
        esperado = {
            Ejecucion.Estado.FALLIDA: EjecucionOrquestador.Estado.DETENIDA,
            Ejecucion.Estado.CANCELADA: EjecucionOrquestador.Estado.CANCELADA,
        }
        for estado, estado_cadena in esperado.items():
            EjecucionOrquestador.objects.all().delete()
            cadena = orquestacion.iniciar(self.orquestador)
            self._terminar(cadena.pasos.get(), estado)
            cadena.refresh_from_db()
            self.assertEqual(cadena.estado, estado_cadena)
            self.assertEqual(cadena.pasos.count(), 1)  # el paso 2 no se encoló
            self.assertIn("paso 1", cadena.mensaje)

    def test_sin_datos_continua_con_el_siguiente(self):
        cadena = orquestacion.iniciar(self.orquestador)
        self._terminar(cadena.pasos.get(), Ejecucion.Estado.SIN_DATOS)
        segunda = cadena.pasos.get(paso=self.paso2)
        self.assertEqual(segunda.estado, Ejecucion.Estado.PENDIENTE)

        self._terminar(segunda, Ejecucion.Estado.EXITOSA)
        cadena.refresh_from_db()
        self.assertEqual(cadena.estado, EjecucionOrquestador.Estado.EXITOSA)
        self.assertIn("1 paso(s) sin datos", cadena.mensaje)

    def test_robot_ocupado(self):
        otro = Robot.objects.create(codigo="OTRO", nombre="Otro")
        self.assertIsNone(orquestacion.robot_ocupado(otro))

        # Con una ejecución en cola
        ejecucion = Ejecucion.objects.create(robot=otro)
        self.assertIn(f"#{ejecucion.pk}", orquestacion.robot_ocupado(otro))
        ejecucion.delete()

        # Con un paso aún no ejecutado en una cadena activa
        PasoOrquestador.objects.create(orquestador=self.orquestador, orden=3, robot=otro)
        otro.credencial = self.robot_a.credencial
        otro.save()
        registro.registrar(type("RobotOtro", (RobotFalso,), {"codigo": "OTRO"}))
        cadena = orquestacion.iniciar(self.orquestador)
        self.assertIn(f"cadena #{cadena.pk}", orquestacion.robot_ocupado(otro))

        # Cuando la cadena se cierra, queda libre
        orquestacion.cancelar(cadena, None)
        self.assertIsNone(orquestacion.robot_ocupado(otro))

    def test_no_inicia_si_un_robot_esta_en_cola(self):
        Ejecucion.objects.create(robot=self.robot_a)
        with self.assertRaises(orquestacion.OrquestadorNoDisponible):
            orquestacion.iniciar(self.orquestador)
        self.assertFalse(EjecucionOrquestador.objects.exists())

    def test_programacion_de_robot_se_omite_si_esta_en_una_cadena(self):
        p = Programacion.objects.create(
            robot=self.robot_a, nombre="r", hora=time(6, 0),
            frecuencia=Programacion.Frecuencia.DIARIA,
        )
        cadena = orquestacion.iniciar(self.orquestador)
        self._terminar(cadena.pasos.get(), Ejecucion.Estado.EXITOSA)  # paso 2 en cola
        Programacion.objects.filter(pk=p.pk).update(proxima_ejecucion=timezone.now())
        self.assertEqual(planificador.encolar_vencidas(), 0)
        self.assertFalse(Ejecucion.objects.filter(programacion=p).exists())

    def test_integracion_con_el_ejecutor(self):
        cadena = orquestacion.iniciar(self.orquestador)
        with sap_simulado():
            ejecutor.ejecutar(cadena.pasos.get())
        self.assertTrue(cadena.pasos.filter(paso=self.paso2, estado=Ejecucion.Estado.PENDIENTE).exists())

    def test_no_inicia_sin_pasos_ni_dos_veces(self):
        vacio = Orquestador.objects.create(nombre="Vacío")
        with self.assertRaises(orquestacion.OrquestadorNoDisponible):
            orquestacion.iniciar(vacio)
        orquestacion.iniciar(self.orquestador)
        with self.assertRaises(orquestacion.OrquestadorNoDisponible):
            orquestacion.iniciar(self.orquestador)

    def test_no_inicia_si_un_robot_no_tiene_login(self):
        self.robot_a.credencial = None
        self.robot_a.save()
        with self.assertRaises(orquestacion.OrquestadorNoDisponible):
            orquestacion.iniciar(self.orquestador)

    def test_cancelar_cadena(self):
        cadena = orquestacion.iniciar(self.orquestador)
        usuario = Usuario.objects.create_user("u@ipesa.com.pe", "x")
        orquestacion.cancelar(cadena, usuario)
        cadena.refresh_from_db()
        self.assertEqual(cadena.estado, EjecucionOrquestador.Estado.CANCELADA)
        self.assertEqual(cadena.pasos.get().estado, Ejecucion.Estado.CANCELADA)

    def test_paso_siguiente_tiene_prioridad_en_la_cola(self):
        from .worker import siguiente_pendiente

        cadena = orquestacion.iniciar(self.orquestador)
        primera = cadena.pasos.get()
        suelta = Ejecucion.objects.create(robot=self.robot_a)  # encolada después de la cadena
        self._terminar(primera, Ejecucion.Estado.EXITOSA)
        self.assertEqual(siguiente_pendiente().paso, self.paso2)
        self.assertNotEqual(siguiente_pendiente(), suelta)

    def test_planificador_lanza_orquestador_y_pasa_parametros_a_robots(self):
        p_orq = Programacion.objects.create(
            orquestador=self.orquestador, nombre="o", hora=time(6, 0),
            frecuencia=Programacion.Frecuencia.DIARIA,
        )
        p_robot = Programacion.objects.create(
            robot=self.robot_a, nombre="r", hora=time(6, 0),
            frecuencia=Programacion.Frecuencia.DIARIA, parametros={"modo": "mes"},
        )
        Programacion.objects.filter(pk=p_orq.pk).update(proxima_ejecucion=timezone.now())
        self.assertEqual(planificador.encolar_vencidas(), 1)
        cadena = EjecucionOrquestador.objects.get()
        self.assertEqual(cadena.programacion, p_orq)
        self.assertEqual(cadena.origen, Ejecucion.Origen.PROGRAMADA)

        EjecucionOrquestador.objects.all().delete()
        Programacion.objects.filter(pk=p_robot.pk).update(proxima_ejecucion=timezone.now())
        self.assertEqual(planificador.encolar_vencidas(), 1)
        self.assertEqual(Ejecucion.objects.get(programacion=p_robot).parametros, {"modo": "mes"})


class VistasOrquestadorTests(TestCase):
    def setUp(self):
        registro.registrar(RobotFalso)
        self.robot = Robot.objects.create(codigo="FALSO", nombre="Robot falso",
                                          credencial=crear_credencial())
        self.admin = Usuario.objects.create_user("admin@ipesa.com.pe", "x", rol=Usuario.Rol.ADMIN)
        self.client.force_login(self.admin)

    def test_crear_orquestador_agregar_pasos_y_ejecutar(self):
        self.client.post(reverse("robots:orquestador_crear"), {"nombre": "Cierre", "activo": "on"})
        orquestador = Orquestador.objects.get()
        url_paso = reverse("robots:paso_crear", args=[orquestador.pk])
        self.client.post(url_paso, {"robot": self.robot.pk, "ej-modo": "uno"})
        self.client.post(url_paso, {"robot": self.robot.pk, "ej-modo": "dos"})
        self.assertEqual(
            list(orquestador.pasos.values_list("orden", "parametros")),
            [(1, {"modo": "uno"}), (2, {"modo": "dos"})],
        )

        segundo = orquestador.pasos.get(orden=2)
        self.client.post(reverse("robots:paso_mover", args=[segundo.pk]), {"direccion": "subir"})
        segundo.refresh_from_db()
        self.assertEqual(segundo.orden, 1)

        respuesta = self.client.post(reverse("robots:orquestador_ejecutar", args=[orquestador.pk]))
        cadena = EjecucionOrquestador.objects.get()
        self.assertRedirects(respuesta, reverse("robots:cadena", args=[cadena.pk]))
        self.assertEqual(cadena.pasos.get().parametros, {"modo": "dos"})

        respuesta = self.client.get(reverse("robots:cadena", args=[cadena.pk]))
        self.assertContains(respuesta, "En espera")
        self.assertContains(self.client.get(reverse("robots:orquestador", args=[orquestador.pk])), "Cierre")
        self.assertContains(self.client.get(reverse("robots:orquestadores")), "Cierre")

    def test_programacion_de_robot_guarda_parametros(self):
        respuesta = self.client.post(reverse("robots:programacion_crear"), {
            "robot": self.robot.pk, "nombre": "Diaria", "frecuencia": "DIARIA",
            "hora": "07:00", "activa": "on", "ej-modo": "mes_en_curso",
        })
        self.assertRedirects(respuesta, reverse("robots:programaciones"))
        self.assertEqual(Programacion.objects.get().parametros, {"modo": "mes_en_curso"})
        self.assertContains(self.client.get(reverse("robots:programaciones")), "mes_en_curso")

    def test_programacion_de_robot_exige_robot(self):
        respuesta = self.client.post(reverse("robots:programacion_crear"), {
            "nombre": "x", "frecuencia": "DIARIA", "hora": "07:00",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors["robot"])
        self.assertFalse(Programacion.objects.exists())

    def test_programar_orquestador_sin_parametros_por_robot(self):
        orquestador = Orquestador.objects.create(nombre="Cierre")
        PasoOrquestador.objects.create(orquestador=orquestador, orden=1, robot=self.robot,
                                       parametros={"modo": "uno"})
        url = reverse("robots:programacion_orquestador_crear")

        respuesta = self.client.get(url, {"orquestador": orquestador.pk})
        self.assertNotContains(respuesta, 'name="ej-modo"')  # no pide parámetros por robot
        self.assertContains(respuesta, "Robot falso")  # muestra los robots en orden

        respuesta = self.client.post(url, {
            "orquestador": orquestador.pk, "nombre": "Cierre diario", "frecuencia": "DIARIA",
            "hora": "06:00", "activa": "on",
        })
        self.assertRedirects(respuesta, reverse("robots:programaciones"))
        p = Programacion.objects.get()
        self.assertEqual((p.orquestador, p.robot, p.parametros), (orquestador, None, {}))

        # Editar por la URL general lleva al formulario del orquestador
        respuesta = self.client.get(reverse("robots:programacion_editar", args=[p.pk]))
        self.assertRedirects(respuesta, reverse("robots:programacion_orquestador_editar", args=[p.pk]))

        respuesta = self.client.get(reverse("robots:pasos_orquestador"), {"orquestador": orquestador.pk})
        self.assertContains(respuesta, "Robot falso")

    def test_fragmento_de_parametros(self):
        respuesta = self.client.get(reverse("robots:parametros_robot"), {"robot": self.robot.pk})
        self.assertContains(respuesta, 'name="ej-modo"')

    def test_editar_programacion_conserva_parametros(self):
        p = Programacion.objects.create(
            robot=self.robot, nombre="p", hora=time(7, 0),
            frecuencia=Programacion.Frecuencia.DIARIA, parametros={"modo": "guardado"},
        )
        respuesta = self.client.get(reverse("robots:programacion_editar", args=[p.pk]))
        self.assertContains(respuesta, 'value="guardado"')
