from django.db import migrations, models


def velas_para_vela1(apps, schema_editor):
    EscalaItem = apps.get_model("scheduling", "EscalaItem")
    EscalaItem.objects.filter(funcao="Velas").update(funcao="Vela1")


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0003_escalaitem_funcao"),
    ]

    operations = [
        migrations.RunPython(velas_para_vela1, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="escalaitem",
            name="funcao",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Cruz", "Cruz"),
                    ("Vela1", "Vela 1"),
                    ("Vela2", "Vela 2"),
                    ("Turibulo", "Turíbulo"),
                    ("Naveta", "Naveta"),
                    ("Missal", "Missal"),
                    ("EntreOsDois", "Entre os dois"),
                    ("Ofertorio", "Ofertório"),
                    ("Assessor", "Assessor"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]
