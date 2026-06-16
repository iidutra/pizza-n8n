from django.db.models import Count, Q
from django.utils import timezone

from apps.attendance.models import Presenca, StatusPresenca
from apps.membership.models import Coroinha, StatusCoroinha
from apps.scheduling.models import Escala, EscalaItem
from apps.training.models import FormacaoConclusao


class RelatorioService:
    @staticmethod
    def dashboard_stats_extra():
        hoje = timezone.now().date()
        inicio_mes = hoje.replace(day=1)

        escalas_mes = Escala.objects.filter(data__gte=inicio_mes, data__lte=hoje).count()
        faltas_mes = Presenca.objects.filter(
            status=StatusPresenca.AUSENTE,
            escala_item__escala__data__gte=inicio_mes,
        ).count()
        from apps.training.models import Formacao

        formacoes_realizadas = Formacao.objects.filter(data__lte=hoje).count()

        return {
            "escalas_mes": escalas_mes,
            "faltas_mes": faltas_mes,
            "formacoes_realizadas": formacoes_realizadas,
        }

    @staticmethod
    def relatorio_geral():
        total_escalas = Escala.objects.count()
        from apps.training.models import Formacao

        formacoes = Formacao.objects.count()

        presencas = Presenca.objects.filter(status=StatusPresenca.PRESENTE).count()
        faltas = Presenca.objects.filter(status=StatusPresenca.AUSENTE).count()
        taxa = round(presencas / (presencas + faltas) * 100) if (presencas + faltas) else 0

        por_status = {
            row["status"]: row["c"]
            for row in Coroinha.objects.values("status").annotate(c=Count("id"))
        }
        por_turma = {
            row["turma"]: row["c"]
            for row in Coroinha.objects.values("turma").annotate(c=Count("id"))
        }

        top_escalados = list(
            EscalaItem.objects.values("coroinha__nome")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )

        return {
            "total_escalas": total_escalas,
            "formacoes_realizadas": formacoes,
            "taxa_presenca": taxa,
            "por_status": por_status,
            "por_turma": por_turma,
            "top_escalados": [
                {"nome": r["coroinha__nome"], "escalas": r["total"]} for r in top_escalados
            ],
        }

    @staticmethod
    def resumo_presenca_coroinhas():
        rows = []
        for c in Coroinha.objects.all():
            itens = EscalaItem.objects.filter(coroinha=c)
            escalas = itens.count()
            presencas = Presenca.objects.filter(
                escala_item__in=itens, status=StatusPresenca.PRESENTE
            ).count()
            faltas = Presenca.objects.filter(
                escala_item__in=itens, status=StatusPresenca.AUSENTE
            ).count()
            registradas = presencas + faltas
            pct = round(presencas / registradas * 100) if registradas else None
            rows.append(
                {
                    "coroinha_id": c.id,
                    "nome": c.nome,
                    "escalas": escalas,
                    "presencas": presencas,
                    "faltas": faltas,
                    "percentual": pct,
                }
            )
        return rows
