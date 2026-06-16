from abc import ABC, abstractmethod
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from apps.membership.models import Coroinha, StatusCoroinha
from apps.scheduling.models import Escala, EscalaItem, FuncaoEscala, ModoEscala


class EscalaStrategy(ABC):
    @abstractmethod
    def selecionar(self, candidatos: list[Coroinha], quantidade: int, escala: Escala) -> list[Coroinha]:
        ...


class SorteioEquilibradoStrategy(EscalaStrategy):
    """Prioriza quem serviu menos nos últimos 90 dias."""

    def selecionar(self, candidatos: list[Coroinha], quantidade: int, escala: Escala) -> list[Coroinha]:
        if not candidatos:
            return []
        desde = timezone.now().date() - timedelta(days=90)
        ids_dia = set(
            EscalaItem.objects.filter(escala__data=escala.data).values_list("coroinha_id", flat=True)
        )
        candidatos = [c for c in candidatos if c.id not in ids_dia]
        if not candidatos:
            return []

        contagem = (
            EscalaItem.objects.filter(
                coroinha_id__in=[c.id for c in candidatos],
                escala__data__gte=desde,
            )
            .values("coroinha_id")
            .annotate(total=Count("id"))
        )
        scores = {row["coroinha_id"]: row["total"] for row in contagem}
        ordenados = sorted(candidatos, key=lambda c: scores.get(c.id, 0))
        return ordenados[:quantidade]


class SelecaoManualStrategy(EscalaStrategy):
    def __init__(self, coroinha_ids: list[int]):
        self.coroinha_ids = coroinha_ids

    def selecionar(self, candidatos: list[Coroinha], quantidade: int, escala: Escala) -> list[Coroinha]:
        candidatos_map = {c.id: c for c in candidatos}
        return [candidatos_map[cid] for cid in self.coroinha_ids if cid in candidatos_map][:quantidade]


class EscalaService:
    @staticmethod
    def candidatos_elegiveis():
        return list(
            Coroinha.objects.filter(status__in=[StatusCoroinha.ATIVO, StatusCoroinha.EM_FORMACAO]).order_by(
                "nome"
            )
        )

    @classmethod
    def montar(
        cls,
        data,
        missa_id: int,
        modo: str,
        quantidade: int,
        usuario,
        coroinha_ids: list[int] | None = None,
        funcoes: dict[str, int] | None = None,
    ) -> Escala:
        from apps.scheduling.models import Missa

        missa = Missa.objects.get(pk=missa_id)
        if Escala.objects.filter(data=data, missa=missa).exists():
            raise ValueError("Já existe escala para esta data e missa.")

        candidatos = cls.candidatos_elegiveis()
        if modo == ModoEscala.SELECAO_MANUAL:
            if not coroinha_ids:
                raise ValueError("Informe os coroinhas para seleção manual.")
            strategy: EscalaStrategy = SelecaoManualStrategy(coroinha_ids)
        else:
            strategy = SorteioEquilibradoStrategy()

        escala = Escala.objects.create(data=data, missa=missa, modo=modo, criado_por=usuario)
        selecionados = strategy.selecionar(candidatos, quantidade, escala)

        if not selecionados:
            escala.delete()
            raise ValueError("Nenhum coroinha disponível para a escala.")

        for i, coroinha in enumerate(selecionados):
            EscalaItem.objects.create(escala=escala, coroinha=coroinha, ordem=i + 1)

        if funcoes:
            cls.atribuir_funcoes(escala, funcoes)

        return escala

    @staticmethod
    def atribuir_funcoes(escala: Escala, funcoes: dict[str, int | None]) -> Escala:
        validas = {c.value for c in FuncaoEscala}
        escala.itens.update(funcao=None)

        coroinhas_atribuidas: set[int] = set()
        for funcao, coroinha_id in funcoes.items():
            if not coroinha_id:
                continue
            if funcao not in validas:
                raise ValueError(f"Função inválida: {funcao}")
            if coroinha_id in coroinhas_atribuidas:
                raise ValueError("O mesmo coroinha não pode ter duas funções na mesma missa.")
            coroinhas_atribuidas.add(coroinha_id)

            item = escala.itens.filter(coroinha_id=coroinha_id).first()
            if not item:
                item = EscalaItem.objects.create(
                    escala=escala,
                    coroinha_id=coroinha_id,
                    ordem=escala.itens.count() + 1,
                )
            item.funcao = funcao
            item.save(update_fields=["funcao"])

        return escala
