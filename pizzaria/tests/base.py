"""Fixtures compartilhadas para testes do bot."""
from decimal import Decimal

from django.test import TestCase

from pizzaria.models import BusinessSettings, Customer, DeliveryFee, Order, OrderItem, Product


class BotTestCase(TestCase):
    """Cria cardápio e config mínimos usados pelo bot."""

    PHONE = '5511999999999'

    @classmethod
    def setUpTestData(cls):
        cls.settings = BusinessSettings.objects.create(
            pk=1,
            business_name='Pizzaria do Negão',
            pix_key='000.000.000-00',
            pix_name='Teste',
            opening_time='19:00',
            closing_time='23:00',
            min_delivery_time=50,
            max_delivery_time=70,
            chatbot_enabled=True,
            promo_active=False,
        )

        cls.products = {}
        catalog = [
            ('Calabresa', 'PIZZA', '40.00'),
            ('Mussarela', 'PIZZA', '35.00'),
            ('Frango com Catupiry', 'PIZZA', '42.00'),
            ('4 Queijos', 'PIZZA', '45.00'),
            ('Portuguesa', 'PIZZA', '43.00'),
            ('Bacon', 'PIZZA', '44.00'),
            ('Baiana', 'PIZZA', '41.00'),
            ('Banana com Canela', 'PIZZA_DOCE', '38.00'),
            ('Coca-Cola 2L', 'BEBIDA', '12.00'),
        ]
        for name, category, price in catalog:
            cls.products[name] = Product.objects.create(
                name=name,
                category=category,
                price=Decimal(price),
                active=True,
            )

        cls.fee_aponia = DeliveryFee.objects.create(
            neighborhood='Aponiã',
            fee=Decimal('8.00'),
            estimated_time=60,
            active=True,
        )
        DeliveryFee.objects.create(
            neighborhood='Planalto',
            fee=Decimal('10.00'),
            estimated_time=65,
            active=True,
        )

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def create_customer_with_order(self, phone=None):
        phone = phone or self.PHONE
        customer = Customer.objects.create(name='Cliente Teste', phone=phone)
        order = Order.objects.create(
            customer=customer,
            order_type='DELIVERY',
            delivery_address='Rua Teste 123',
            neighborhood='Aponiã',
            delivery_fee=Decimal('8.00'),
            subtotal=Decimal('40.00'),
            total=Decimal('48.00'),
            payment_method='PIX',
            status='COMPLETED',
        )
        OrderItem.objects.create(
            order=order,
            product=self.products['Calabresa'],
            quantity=1,
            unit_price=Decimal('40.00'),
        )
        return customer, order
