from datetime import time

from django.core.management.base import BaseCommand

from apps.scheduling.models import DiaSemana, Missa

MISSAS_PADRAO = [
    ("Domingo 08h", DiaSemana.DOMINGO, None, time(8, 0)),
    ("Domingo 18h30", DiaSemana.DOMINGO, None, time(18, 30)),
    ("Dia 13 — 06h", None, 13, time(6, 0)),
    ("Dia 13 — 09h", None, 13, time(9, 0)),
    ("Dia 13 — 12h", None, 13, time(12, 0)),
    ("Dia 13 — 18h", None, 13, time(18, 0)),
]


class Command(BaseCommand):
    help = "Cria missas padrão da paróquia."

    def handle(self, *args, **options):
        for nome, dia_semana, dia_mes, horario in MISSAS_PADRAO:
            _, created = Missa.objects.update_or_create(
                nome=nome,
                defaults={
                    "dia_semana": dia_semana,
                    "dia_mes": dia_mes,
                    "horario": horario,
                    "ativa": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Missa criada: {nome}"))
            else:
                self.stdout.write(f"Missa atualizada: {nome}")
