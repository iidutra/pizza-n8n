from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("membership", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="coroinha",
            name="foto",
            field=models.ImageField(blank=True, null=True, upload_to="coroinhas/fotos/"),
        ),
        migrations.AddField(
            model_name="inscricao",
            name="foto_pendente",
            field=models.ImageField(blank=True, null=True, upload_to="inscricoes/fotos/"),
        ),
    ]
