"""Cada robot pasa a usar un login SAP en vez de una conexión.

Se asigna a cada robot el login creado a partir de su conexión anterior
(migración sap 0002), así sigue entrando con el mismo usuario.
"""
import django.db.models.deletion
from django.db import migrations, models


def asignar_credencial(apps, schema_editor):
    Robot = apps.get_model("robots", "Robot")
    CredencialSAP = apps.get_model("sap", "CredencialSAP")
    for robot in Robot.objects.exclude(conexion=None):
        robot.credencial = (
            CredencialSAP.objects.filter(conexion_id=robot.conexion_id).order_by("pk").first()
        )
        robot.save(update_fields=["credencial"])


def restaurar_conexion(apps, schema_editor):
    Robot = apps.get_model("robots", "Robot")
    for robot in Robot.objects.exclude(credencial=None).select_related("credencial"):
        robot.conexion_id = robot.credencial.conexion_id
        robot.save(update_fields=["conexion"])


class Migration(migrations.Migration):

    dependencies = [
        ("robots", "0002_control_worker"),
        ("sap", "0002_credencialsap"),
    ]

    operations = [
        migrations.AddField(
            model_name="robot",
            name="credencial",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="robots", to="sap.credencialsap", verbose_name="login SAP",
                help_text="Usuario SAP con el que entra este robot.",
            ),
        ),
        migrations.RunPython(asignar_credencial, restaurar_conexion),
        migrations.RemoveField(model_name="robot", name="conexion"),
    ]
