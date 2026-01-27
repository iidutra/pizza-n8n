from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(default='Pizzaria do Negao', max_length=255, verbose_name='Nome do Negocio')),
                ('pix_key', models.CharField(max_length=255, verbose_name='Chave Pix')),
                ('pix_name', models.CharField(max_length=255, verbose_name='Nome do Pix')),
                ('opening_time', models.TimeField(verbose_name='Horario de Abertura')),
                ('closing_time', models.TimeField(verbose_name='Horario de Fechamento')),
                ('min_delivery_time', models.IntegerField(default=50, verbose_name='Tempo Minimo de Entrega (min)')),
                ('max_delivery_time', models.IntegerField(default=70, verbose_name='Tempo Maximo de Entrega (min)')),
                ('menu_image', models.ImageField(blank=True, upload_to='config/', verbose_name='Imagem do Cardapio')),
                ('promo_image', models.ImageField(blank=True, upload_to='config/', verbose_name='Imagem da Promocao')),
                ('promo_text', models.TextField(blank=True, verbose_name='Texto da Promocao')),
                ('promo_active', models.BooleanField(default=False, verbose_name='Promocao Ativa')),
            ],
            options={
                'verbose_name': 'Configuracao',
                'verbose_name_plural': 'Configuracoes',
            },
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Nome')),
                ('phone', models.CharField(max_length=20, unique=True, verbose_name='Telefone')),
                ('address', models.TextField(blank=True, verbose_name='Endereco')),
                ('neighborhood', models.CharField(blank=True, max_length=100, verbose_name='Bairro')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={
                'verbose_name': 'Cliente',
                'verbose_name_plural': 'Clientes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DeliveryFee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('neighborhood', models.CharField(max_length=100, unique=True, verbose_name='Bairro')),
                ('fee', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Taxa')),
                ('estimated_time', models.IntegerField(default=60, verbose_name='Tempo estimado (min)')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo')),
            ],
            options={
                'verbose_name': 'Taxa de Entrega',
                'verbose_name_plural': 'Taxas de Entrega',
                'ordering': ['neighborhood'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, verbose_name='Nome')),
                ('description', models.TextField(blank=True, verbose_name='Descricao')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Preco')),
                ('category', models.CharField(choices=[('PIZZA', 'Pizza'), ('BEBIDA', 'Bebida'), ('ADICIONAL', 'Adicional')], max_length=20, verbose_name='Categoria')),
                ('image', models.ImageField(blank=True, upload_to='products/', verbose_name='Imagem')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={
                'verbose_name': 'Produto',
                'verbose_name_plural': 'Produtos',
                'ordering': ['category', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('NEW', 'Novo'), ('AWAITING_PAYMENT', 'Aguardando Pagamento'), ('PREPARING', 'Em Preparo'), ('OUT_FOR_DELIVERY', 'Saiu para Entrega'), ('READY_FOR_PICKUP', 'Pronto para Retirada'), ('COMPLETED', 'Finalizado'), ('CANCELLED', 'Cancelado')], default='NEW', max_length=20, verbose_name='Status')),
                ('order_type', models.CharField(choices=[('DELIVERY', 'Entrega'), ('PICKUP', 'Retirada')], default='DELIVERY', max_length=20, verbose_name='Tipo')),
                ('delivery_address', models.TextField(blank=True, verbose_name='Endereco de Entrega')),
                ('neighborhood', models.CharField(blank=True, max_length=100, verbose_name='Bairro')),
                ('delivery_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Taxa de Entrega')),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Subtotal')),
                ('total', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Total')),
                ('payment_status', models.CharField(choices=[('PENDING', 'Pendente'), ('RECEIPT_RECEIVED', 'Comprovante Recebido'), ('CONFIRMED', 'Confirmado'), ('PAY_ON_DELIVERY', 'Pagar na Entrega')], default='PENDING', max_length=20, verbose_name='Status Pagamento')),
                ('payment_receipt', models.ImageField(blank=True, upload_to='receipts/', verbose_name='Comprovante')),
                ('notes', models.TextField(blank=True, verbose_name='Observacoes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='pizzaria.customer', verbose_name='Cliente')),
            ],
            options={
                'verbose_name': 'Pedido',
                'verbose_name_plural': 'Pedidos',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField(default=1, verbose_name='Quantidade')),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Preco Unitario')),
                ('notes', models.TextField(blank=True, verbose_name='Observacoes')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pizzaria.order', verbose_name='Pedido')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pizzaria.product', verbose_name='Produto')),
            ],
            options={
                'verbose_name': 'Item do Pedido',
                'verbose_name_plural': 'Itens do Pedido',
            },
        ),
    ]
