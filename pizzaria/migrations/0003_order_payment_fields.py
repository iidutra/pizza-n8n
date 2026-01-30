from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pizzaria', '0002_alter_product_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[('PIX', 'Pix'), ('CASH', 'Dinheiro'), ('CREDIT', 'Cartão Crédito'), ('DEBIT', 'Cartão Débito')],
                max_length=20,
                null=True,
                verbose_name='Forma de Pagamento'
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='change_for',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Troco para'
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='card_fee',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name='Taxa Maquininha'
            ),
        ),
    ]
