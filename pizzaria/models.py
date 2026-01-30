from django.db import models


class Customer(models.Model):
    """Cliente da pizzaria."""
    name = models.CharField(max_length=255, verbose_name='Nome')
    phone = models.CharField(max_length=20, unique=True, verbose_name='Telefone')
    address = models.TextField(blank=True, verbose_name='Endereco')
    neighborhood = models.CharField(max_length=100, blank=True, verbose_name='Bairro')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.phone}"


class Product(models.Model):
    """Produto do cardapio."""
    CATEGORY_CHOICES = [
        ('PIZZA', 'Pizza'),
        ('PIZZA_DOCE', 'Pizza Doce'),
        ('BEBIDA', 'Bebida'),
        ('ADICIONAL', 'Adicional'),
    ]

    name = models.CharField(max_length=255, verbose_name='Nome')
    description = models.TextField(blank=True, verbose_name='Descricao')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Preco')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='Categoria')
    image = models.ImageField(upload_to='products/', blank=True, verbose_name='Imagem')
    active = models.BooleanField(default=True, verbose_name='Ativo')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} - R$ {self.price}"


class DeliveryFee(models.Model):
    """Taxa de entrega por bairro."""
    neighborhood = models.CharField(max_length=100, unique=True, verbose_name='Bairro')
    fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Taxa')
    estimated_time = models.IntegerField(default=60, verbose_name='Tempo estimado (min)')
    active = models.BooleanField(default=True, verbose_name='Ativo')

    class Meta:
        verbose_name = 'Taxa de Entrega'
        verbose_name_plural = 'Taxas de Entrega'
        ordering = ['neighborhood']

    def __str__(self):
        return f"{self.neighborhood} - R$ {self.fee}"


class Order(models.Model):
    """Pedido do cliente."""
    STATUS_CHOICES = [
        ('NEW', 'Novo'),
        ('AWAITING_PAYMENT', 'Aguardando Pagamento'),
        ('PREPARING', 'Em Preparo'),
        ('OUT_FOR_DELIVERY', 'Saiu para Entrega'),
        ('READY_FOR_PICKUP', 'Pronto para Retirada'),
        ('COMPLETED', 'Finalizado'),
        ('CANCELLED', 'Cancelado'),
    ]

    ORDER_TYPE_CHOICES = [
        ('DELIVERY', 'Entrega'),
        ('PICKUP', 'Retirada'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pendente'),
        ('RECEIPT_RECEIVED', 'Comprovante Recebido'),
        ('CONFIRMED', 'Confirmado'),
        ('PAY_ON_DELIVERY', 'Pagar na Entrega'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('PIX', 'Pix'),
        ('CASH', 'Dinheiro'),
        ('CREDIT', 'Cartão Crédito'),
        ('DEBIT', 'Cartão Débito'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='orders', verbose_name='Cliente')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW', verbose_name='Status')
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='DELIVERY', verbose_name='Tipo')
    delivery_address = models.TextField(blank=True, verbose_name='Endereco de Entrega')
    neighborhood = models.CharField(max_length=100, blank=True, verbose_name='Bairro')
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Taxa de Entrega')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Subtotal')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Total')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING', verbose_name='Status Pagamento')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True, verbose_name='Forma de Pagamento')
    payment_receipt = models.ImageField(upload_to='receipts/', blank=True, verbose_name='Comprovante')
    change_for = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name='Troco para')
    card_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Taxa Maquininha')
    notes = models.TextField(blank=True, verbose_name='Observacoes')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Atualizado em')

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-created_at']

    def __str__(self):
        return f"Pedido #{self.id} - {self.customer.name}"

    def calculate_totals(self):
        """Calcula subtotal e total do pedido."""
        self.subtotal = sum(item.unit_price * item.quantity for item in self.items.all())
        self.total = self.subtotal + self.delivery_fee
        return self.total


class OrderItem(models.Model):
    """Item de um pedido."""
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE, verbose_name='Pedido')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Produto')
    quantity = models.IntegerField(default=1, verbose_name='Quantidade')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Preco Unitario')
    notes = models.TextField(blank=True, verbose_name='Observacoes')

    class Meta:
        verbose_name = 'Item do Pedido'
        verbose_name_plural = 'Itens do Pedido'

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    @property
    def total_price(self):
        return self.unit_price * self.quantity


class BusinessSettings(models.Model):
    """Configuracoes do negocio."""
    business_name = models.CharField(max_length=255, default="Pizzaria do Negao", verbose_name='Nome do Negocio')
    pix_key = models.CharField(max_length=255, verbose_name='Chave Pix')
    pix_name = models.CharField(max_length=255, verbose_name='Nome do Pix')
    opening_time = models.TimeField(verbose_name='Horario de Abertura')
    closing_time = models.TimeField(verbose_name='Horario de Fechamento')
    min_delivery_time = models.IntegerField(default=50, verbose_name='Tempo Minimo de Entrega (min)')
    max_delivery_time = models.IntegerField(default=70, verbose_name='Tempo Maximo de Entrega (min)')
    menu_image = models.ImageField(upload_to='config/', blank=True, verbose_name='Imagem do Cardapio')
    promo_image = models.ImageField(upload_to='config/', blank=True, verbose_name='Imagem da Promocao')
    promo_text = models.TextField(blank=True, verbose_name='Texto da Promocao')
    promo_active = models.BooleanField(default=False, verbose_name='Promocao Ativa')

    class Meta:
        verbose_name = 'Configuracao'
        verbose_name_plural = 'Configuracoes'

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        if not self.pk and BusinessSettings.objects.exists():
            return
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        settings, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'pix_key': '013.317.962-10',
                'pix_name': 'Jefferson Pereira de Moura',
                'opening_time': '18:00',
                'closing_time': '23:59',
            }
        )
        return settings
