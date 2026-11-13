"""Separa los logins (usuario + contraseña) de la conexión SAP.

Cada conexión existente genera un login con su mismo usuario, contraseña
cifrada y opción de finalizar otras sesiones, así no hay que volver a
ingresar nada.
"""
import django.db.models.deletion
from django.db import migrations, models


def copiar_credenciales(apps, schema_editor):
    ConexionSAP = apps.get_model("sap", "ConexionSAP")
    CredencialSAP = apps.get_model("sap", "CredencialSAP")
    for conexion in ConexionSAP.objects.all():
        CredencialSAP.objects.create(
            conexion=conexion,
            usuario=conexion.usuario,
            clave_cifrada=conexion.clave_cifrada,
            finalizar_otras_sesiones=conexion.finalizar_otras_sesiones,
            activa=True,
        )


def restaurar_credenciales(apps, schema_editor):
    ConexionSAP = apps.get_model("sap", "ConexionSAP")
    for conexion in ConexionSAP.objects.all():
        credencial = conexion.credenciales.order_by("pk").first()
        if credencial:
            conexion.usuario = credencial.usuario
            conexion.clave_cifrada = credencial.clave_cifrada
            conexion.finalizar_otras_sesiones = credencial.finalizar_otras_sesiones
            conexion.save()


class Migration(migrations.Migration):

    dependencies = [
        ("sap", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CredencialSAP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("usuario", models.CharField(max_length=40)),
                ("clave_cifrada", models.TextField(editable=False)),
                ("descripcion", models.CharField(blank=True, help_text="Para qué se usa este login, p. ej. 'RPAs de ventas'.", max_length=120, verbose_name="descripción")),
                ("finalizar_otras_sesiones", models.BooleanField(default=True, help_text="Si el usuario tiene sesión abierta en otro equipo: finalizarla y continuar. Si está desmarcado, el robot se detiene.")),
                ("activa", models.BooleanField(default=True)),
                ("actualizada", models.DateTimeField(auto_now=True)),
                ("conexion", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="credenciales", to="sap.conexionsap", verbose_name="conexión SAP")),
            ],
            options={
                "verbose_name": "login SAP",
                "verbose_name_plural": "logins SAP",
                "ordering": ["conexion__nombre", "usuario"],
                "constraints": [models.UniqueConstraint(fields=("conexion", "usuario"), name="credencial_unica_por_conexion")],
            },
        ),
        migrations.RunPython(copiar_credenciales, restaurar_credenciales),
        # Valor por defecto solo para que la reversa pueda recrear las columnas
        migrations.AlterField(
            model_name="conexionsap", name="usuario",
            field=models.CharField(max_length=40, default=""),
        ),
        migrations.AlterField(
            model_name="conexionsap", name="clave_cifrada",
            field=models.TextField(editable=False, default=""),
        ),
        migrations.RemoveField(model_name="conexionsap", name="usuario"),
        migrations.RemoveField(model_name="conexionsap", name="clave_cifrada"),
        migrations.RemoveField(model_name="conexionsap", name="finalizar_otras_sesiones"),
    ]
