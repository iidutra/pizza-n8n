from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="missa",
            name="dia_mes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Dia do mês (ex.: 13) para missas mensais fixas.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="missa",
            name="dia_semana",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Domingo", "Domingo"),
                    ("Segunda", "Segunda"),
                    ("Terca", "Terça"),
                    ("Quarta", "Quarta"),
                    ("Quinta", "Quinta"),
                    ("Sexta", "Sexta"),
                    ("Sabado", "Sábado"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="missa",
            constraint=models.CheckConstraint(
                condition=models.Q(("dia_semana__isnull", False), ("dia_mes__isnull", False), _connector="OR"),
                name="missa_dia_semana_ou_dia_mes",
            ),
        ),
    ]
