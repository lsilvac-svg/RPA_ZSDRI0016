from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Usuario


class UsuarioTests(TestCase):
    def test_rechaza_correo_de_otro_dominio(self):
        with self.assertRaises(ValidationError):
            Usuario.objects.create_user("alguien@gmail.com", "Clave-segura-123")

    def test_normaliza_correo_y_rol_admin_da_acceso_staff(self):
        admin = Usuario.objects.create_user(
            "Jefe@IPESA.com.pe", "Clave-segura-123", rol=Usuario.Rol.ADMIN
        )
        self.assertEqual(admin.email, "jefe@ipesa.com.pe")
        self.assertTrue(admin.es_admin)
        self.assertTrue(admin.is_staff)


class LoginTests(TestCase):
    def setUp(self):
        Usuario.objects.create_user("usuario@ipesa.com.pe", "Clave-segura-123")

    def test_login_con_correo_corporativo(self):
        respuesta = self.client.post(reverse("login"), {
            "username": "Usuario@ipesa.com.pe", "password": "Clave-segura-123",
        })
        self.assertRedirects(respuesta, reverse("core:panel"))

    def test_login_rechaza_otro_dominio(self):
        respuesta = self.client.post(reverse("login"), {
            "username": "usuario@gmail.com", "password": "Clave-segura-123",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Solo pueden ingresar correos @ipesa.com.pe")

    def test_paginas_requieren_login(self):
        respuesta = self.client.get(reverse("core:panel"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("login"), respuesta.url)


class PerfilesTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user("usuario@ipesa.com.pe", "x")
        self.admin = Usuario.objects.create_user("admin@ipesa.com.pe", "x", rol=Usuario.Rol.ADMIN)

    def test_usuario_no_accede_a_administracion(self):
        self.client.force_login(self.usuario)
        for nombre in ("cuentas:lista", "sap:lista", "robots:programaciones"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, nombre)

    def test_admin_accede_a_administracion(self):
        self.client.force_login(self.admin)
        for nombre in ("cuentas:lista", "sap:lista", "robots:programaciones"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_usuario_accede_a_operacion(self):
        self.client.force_login(self.usuario)
        for nombre in ("core:panel", "robots:monitor", "robots:ejecuciones", "robots:lista"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)
