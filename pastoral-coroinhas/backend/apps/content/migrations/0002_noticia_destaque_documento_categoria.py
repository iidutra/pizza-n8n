from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="noticia",
            name="destaque",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documento",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("Liturgia", "Liturgia"),
                    ("Formacao", "Formação"),
                    ("Ritual", "Ritual"),
                    ("Outro", "Outro"),
                ],
                default="Outro",
                max_length=20,
            ),
        ),
    ]
