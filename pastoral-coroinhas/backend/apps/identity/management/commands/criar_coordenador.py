from django.core.management.base import BaseCommand

from apps.identity.models import TipoPerfil, Usuario


class Command(BaseCommand):
    help = "Cria o coordenador inicial do sistema."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="E-mail do coordenador")
        parser.add_argument("--nome", default="Coordenador", help="Nome completo")
        parser.add_argument("--senha", required=True, help="Senha inicial")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        if Usuario.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f"Usuário {email} já existe."))
            return

        usuario = Usuario.objects.create_user(
            email=email,
            nome=options["nome"],
            password=options["senha"],
            tipo_perfil=TipoPerfil.COORDENADOR,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Coordenador criado: {usuario.nome} ({usuario.email})"))
