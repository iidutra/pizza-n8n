from django.utils import timezone

from apps.attendance.models import Presenca, StatusPresenca
from apps.scheduling.models import Escala, EscalaItem
from apps.training.models import Formacao, FormacaoConclusao


class MensagemTemplate:
    @staticmethod
    def render(corpo: str, nome: str, escala: str = "", idade: str = "") -> str:
        return (
            corpo.replace("{nome}", nome)
            .replace("{escala}", escala)
            .replace("{idade}", idade)
        )


class ComunicacaoService:
    @classmethod
    def enviar(cls, canal: str, corpo: str, coroinha_ids: list[int], usuario) -> "Mensagem":
        from apps.communication.models import Mensagem
        from apps.membership.models import Coroinha

        coroinhas = Coroinha.objects.filter(id__in=coroinha_ids)
        if not coroinhas.exists():
            raise ValueError("Nenhum destinatário válido.")

        mensagem = Mensagem.objects.create(
            canal=canal,
            corpo=corpo,
            enviada_por=usuario,
            simulacao=True,
        )
        mensagem.destinatarios.set(coroinhas)
        return mensagem

    @staticmethod
    def preview(corpo: str, coroinha_id: int) -> str:
        from apps.membership.models import Coroinha

        coroinha = Coroinha.objects.get(pk=coroinha_id)
        proxima = (
            EscalaItem.objects.filter(coroinha=coroinha, escala__data__gte=timezone.now().date())
            .select_related("escala", "escala__missa")
            .order_by("escala__data")
            .first()
        )
        escala_txt = ""
        if proxima:
            escala_txt = f"{proxima.escala.data:%d/%m/%Y} — {proxima.escala.missa.nome}"
        return MensagemTemplate.render(corpo, coroinha.nome, escala_txt, str(coroinha.idade))
