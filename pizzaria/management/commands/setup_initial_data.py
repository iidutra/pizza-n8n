from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pizzaria.models import Product, DeliveryFee, BusinessSettings


class Command(BaseCommand):
    help = 'Configura dados iniciais do sistema (produtos, taxas, configuracoes)'

    def handle(self, *args, **options):
        self.stdout.write('Configurando dados iniciais...')

        # Criar superusuario se nao existir
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@pizzaria.com', 'admin123')
            self.stdout.write(self.style.SUCCESS('Superusuario criado: admin / admin123'))
        else:
            self.stdout.write('Superusuario ja existe')

        # Texto da promocao
        promo_text = """🍕 Pizzaria do Negão 🍕

Chegou a promoção pra você matar a fome com sabor! 😋

✅ Promoção: 2 Pizzas Grandes por apenas R$ 55,00
🚗 Delivery ou 🛍️ Retirada
📍 Taxa de entrega conforme o bairro

📲 Peça agora no WhatsApp: (69) 9 9363-9552

A Pizzaria do Negão agradece a preferência! ❤️🍕"""

        # Configuracoes do negocio
        settings, created = BusinessSettings.objects.get_or_create(
            pk=1,
            defaults={
                'business_name': 'Pizzaria do Negão',
                'pix_key': '013.317.962-10',
                'pix_name': 'Jefferson Pereira de Moura',
                'opening_time': '18:00',
                'closing_time': '23:59',
                'min_delivery_time': 50,
                'max_delivery_time': 70,
                'promo_text': promo_text,
                'promo_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Configuracoes do negocio criadas'))
        else:
            # Atualiza promoção se já existe
            settings.promo_text = promo_text
            settings.promo_active = True
            settings.save()
            self.stdout.write(self.style.SUCCESS('Promocao atualizada!'))

        # Produtos - Pizzas (conforme cardápio da imagem)
        pizzas = [
            {'name': 'Pizza Mussarela', 'description': 'Molho, mussarela, tomate e orégano', 'price': 30.00},
            {'name': 'Pizza Calabresa', 'description': 'Molho, mussarela, calabresa, cebola e orégano', 'price': 35.00},
            {'name': 'Pizza Frango com Catupiry', 'description': 'Molho, mussarela, frango, catupiry e orégano', 'price': 38.00},
            {'name': 'Pizza Frango com Cheddar', 'description': 'Molho, mussarela, frango, cheddar e orégano', 'price': 38.00},
            {'name': 'Pizza Frango com Milho', 'description': 'Molho, mussarela, frango, milho e orégano', 'price': 38.00},
            {'name': 'Pizza Calabresa com Catupiry', 'description': 'Molho, mussarela, calabresa, catupiry e orégano', 'price': 38.00},
            {'name': 'Pizza Atum', 'description': 'Molho, mussarela, atum, cebola e orégano', 'price': 40.00},
            {'name': 'Pizza Palmito', 'description': 'Molho, mussarela, palmito, tomate e orégano', 'price': 38.00},
            {'name': 'Pizza Francesa', 'description': 'Molho, mussarela, presuntado, catupiry e orégano', 'price': 38.00},
            {'name': 'Pizza Baiana', 'description': 'Molho, mussarela, calabresa, pimenta calabresa e orégano', 'price': 38.00},
            {'name': 'Pizza Mexicana', 'description': 'Molho, mussarela, calabresa, pimenta calabresa, bacon e orégano', 'price': 40.00},
            {'name': 'Pizza Bacon', 'description': 'Molho, mussarela, bacon, tomate e orégano', 'price': 38.00},
            {'name': 'Pizza Bauru', 'description': 'Molho, presunto, mussarela, tomate e orégano', 'price': 40.00},
            {'name': 'Pizza Portuguesa', 'description': 'Molho, presunto, mussarela, milho, tomate, pimentão, calabresa e orégano', 'price': 40.00},
            {'name': 'Pizza 4 Queijos', 'description': 'Molho, mussarela, cheddar, catupiry, parmesão e orégano', 'price': 42.00},
        ]

        for pizza_data in pizzas:
            product, created = Product.objects.get_or_create(
                name=pizza_data['name'],
                defaults={
                    'description': pizza_data['description'],
                    'price': pizza_data['price'],
                    'category': 'PIZZA',
                    'active': True
                }
            )
            if created:
                self.stdout.write(f'  Pizza criada: {product.name}')

        # Produtos - Pizzas Doces (conforme cardápio da imagem)
        pizzas_doces = [
            {'name': 'Pizza Brigadeiro', 'description': 'Molho, chocolate ao leite e granulado', 'price': 40.00},
            {'name': 'Pizza Prestígio', 'description': 'Molho, chocolate ao leite e coco ralado', 'price': 40.00},
            {'name': 'Pizza Banana com Canela', 'description': 'Molho, banana, canela e leite condensado', 'price': 40.00},
        ]

        for doce_data in pizzas_doces:
            product, created = Product.objects.get_or_create(
                name=doce_data['name'],
                defaults={
                    'description': doce_data['description'],
                    'price': doce_data['price'],
                    'category': 'PIZZA_DOCE',
                    'active': True
                }
            )
            if created:
                self.stdout.write(f'  Pizza doce criada: {product.name}')

        # Produtos - Bebidas
        bebidas = [
            {'name': 'Coca-Cola 1,5L', 'price': 12.00},
            {'name': 'Tuchaua 2L', 'price': 10.00},
            {'name': 'Pepsi 2L', 'price': 14.00},
            {'name': 'Guaraná Antarctica 2L', 'price': 12.00},
            {'name': 'Fanta Laranja 2L', 'price': 11.00},
            {'name': 'Água Mineral 500ml', 'price': 4.00},
        ]

        for bebida_data in bebidas:
            product, created = Product.objects.get_or_create(
                name=bebida_data['name'],
                defaults={
                    'price': bebida_data['price'],
                    'category': 'BEBIDA',
                    'active': True
                }
            )
            if created:
                self.stdout.write(f'  Bebida criada: {product.name}')

        # Taxas de entrega por bairro
        bairros = [
            {'neighborhood': 'Centro', 'fee': 5.00, 'estimated_time': 30},
            {'neighborhood': 'Jardim América', 'fee': 6.00, 'estimated_time': 35},
            {'neighborhood': 'Vila Nova', 'fee': 7.00, 'estimated_time': 40},
            {'neighborhood': 'Parque Industrial', 'fee': 8.00, 'estimated_time': 45},
            {'neighborhood': 'Cohab', 'fee': 6.00, 'estimated_time': 35},
            {'neighborhood': 'Jardim Europa', 'fee': 7.00, 'estimated_time': 40},
            {'neighborhood': 'Vila Maria', 'fee': 5.50, 'estimated_time': 30},
            {'neighborhood': 'Conjunto Habitacional', 'fee': 8.00, 'estimated_time': 50},
        ]

        for bairro_data in bairros:
            fee, created = DeliveryFee.objects.get_or_create(
                neighborhood=bairro_data['neighborhood'],
                defaults={
                    'fee': bairro_data['fee'],
                    'estimated_time': bairro_data['estimated_time'],
                    'active': True
                }
            )
            if created:
                self.stdout.write(f'  Taxa criada: {fee.neighborhood}')

        self.stdout.write(self.style.SUCCESS('\nDados iniciais configurados com sucesso!'))
        self.stdout.write(self.style.WARNING('\nCredenciais de acesso:'))
        self.stdout.write('  Usuario: admin')
        self.stdout.write('  Senha: admin123')
        self.stdout.write('\nAcesse: http://localhost:8000/')
