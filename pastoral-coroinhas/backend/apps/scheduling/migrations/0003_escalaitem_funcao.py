from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0002_missa_dia_mes"),
    ]

    operations = [
        migrations.AddField(
            model_name="escalaitem",
            name="funcao",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Cruz", "Cruz"),
                    ("Velas", "Velas"),
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
        migrations.AddConstraint(
            model_name="escalaitem",
            constraint=models.UniqueConstraint(
                condition=models.Q(("funcao__isnull", False)),
                fields=("escala", "funcao"),
                name="escala_funcao_unica",
            ),
        ),
    ]
