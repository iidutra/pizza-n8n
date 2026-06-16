from django.utils import timezone

from apps.membership.models import Coroinha, StatusCoroinha


class CoroinhaService:
    @staticmethod
    def aniversariantes_do_mes(mes: int | None = None):
        mes = mes or timezone.now().month
        return (
            Coroinha.objects.filter(
                data_nascimento__month=mes,
                status__in=(StatusCoroinha.ATIVO, StatusCoroinha.EM_FORMACAO),
            )
            .order_by("data_nascimento__day", "nome")
        )
