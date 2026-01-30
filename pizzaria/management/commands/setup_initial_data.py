from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pizzaria.models import BusinessSettings


class Command(BaseCommand):
    help = 'Configura dados iniciais do sistema (apenas usuario admin e configuracoes)'

    def handle(self, *args, **options):
        self.stdout.write('Configurando dados iniciais...')

        # Criar superusuario se nao existir
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@pizzaria.com', 'admin123')
            self.stdout.write(self.style.SUCCESS('Superusuario criado: admin / admin123'))
        else:
            self.stdout.write('Superusuario ja existe')

        # Configuracoes do negocio (apenas se nao existir)
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
                'promo_active': False,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Configuracoes do negocio criadas'))
        else:
            self.stdout.write('Configuracoes ja existem, nao alterando')

        # Pizzas, bebidas e taxas de entrega devem ser cadastradas pelo painel admin
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('IMPORTANTE: Cadastre os produtos pelo painel:'))
        self.stdout.write('  - Pizzas: Menu > Adicionar produto (categoria PIZZA)')
        self.stdout.write('  - Pizzas Doces: Menu > Adicionar produto (categoria PIZZA_DOCE)')
        self.stdout.write('  - Bebidas: Menu > Adicionar produto (categoria BEBIDA)')
        self.stdout.write('  - Taxas de Entrega: Taxas de Entrega > Adicionar')

        self.stdout.write(self.style.SUCCESS('\nDados iniciais configurados!'))
        self.stdout.write(self.style.WARNING('\nCredenciais de acesso:'))
        self.stdout.write('  Usuario: admin')
        self.stdout.write('  Senha: admin123')
