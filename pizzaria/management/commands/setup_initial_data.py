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

        # Configuracoes do negocio
        settings, created = BusinessSettings.objects.get_or_create(
            pk=1,
            defaults={
                'business_name': 'Pizzaria do Negao',
                'pix_key': '013.317.962-10',
                'pix_name': 'Jefferson Pereira de Moura',
                'opening_time': '18:00',
                'closing_time': '23:59',
                'min_delivery_time': 50,
                'max_delivery_time': 70,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Configuracoes do negocio criadas'))
        else:
            self.stdout.write('Configuracoes ja existem')

        # Produtos - Pizzas
        pizzas = [
            {'name': 'Pizza Calabresa', 'description': 'Molho, mussarela, calabresa e cebola', 'price': 35.00},
            {'name': 'Pizza Frango com Catupiry', 'description': 'Molho, mussarela, frango desfiado e catupiry', 'price': 38.00},
            {'name': 'Pizza Portuguesa', 'description': 'Molho, mussarela, presunto, ovo, cebola, azeitona e ervilha', 'price': 40.00},
            {'name': 'Pizza Marguerita', 'description': 'Molho, mussarela, tomate e manjericao', 'price': 35.00},
            {'name': 'Pizza Quatro Queijos', 'description': 'Molho, mussarela, provolone, parmesao e gorgonzola', 'price': 42.00},
            {'name': 'Pizza Bacon', 'description': 'Molho, mussarela e bacon crocante', 'price': 38.00},
            {'name': 'Pizza Pepperoni', 'description': 'Molho, mussarela e pepperoni', 'price': 40.00},
            {'name': 'Pizza Mussarela', 'description': 'Molho e mussarela', 'price': 30.00},
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

        # Produtos - Bebidas
        bebidas = [
            {'name': 'Coca-Cola 1,5L', 'price': 12.00},
            {'name': 'Tuchaua 2L', 'price': 10.00},
            {'name': 'Pepsi 2L', 'price': 14.00},
            {'name': 'Guarana Antarctica 2L', 'price': 12.00},
            {'name': 'Fanta Laranja 2L', 'price': 11.00},
            {'name': 'Agua Mineral 500ml', 'price': 4.00},
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
            {'neighborhood': 'Jardim America', 'fee': 6.00, 'estimated_time': 35},
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
