from datetime import date

import pytest
from rest_framework import status

from apps.scheduling.models import FuncaoEscala
from apps.scheduling.services.escala_service import EscalaService
from apps.scheduling.services.relatorio_escala_service import RelatorioEscalaService

pytestmark = pytest.mark.django_db


class TestEscalaService:
    def test_montar_escala_automatica(self, coordenador, missa_domingo, coroinha):
        escala = EscalaService.montar(
            data=date(2026, 6, 15),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=1,
            usuario=coordenador,
        )
        assert escala.itens.count() == 1
        assert escala.itens.first().coroinha_id == coroinha.id

    def test_montar_escala_duplicada_falha(self, coordenador, missa_domingo, coroinha):
        EscalaService.montar(
            data=date(2026, 6, 15),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=1,
            usuario=coordenador,
        )
        with pytest.raises(ValueError, match="Já existe escala"):
            EscalaService.montar(
                data=date(2026, 6, 15),
                missa_id=missa_domingo.id,
                modo="SorteioAutomatico",
                quantidade=1,
                usuario=coordenador,
            )

    def test_atribuir_duas_velas(self, coordenador, missa_domingo, coroinha):
        coroinha2 = coroinha.__class__.objects.create(
            nome="Maria Teste",
            data_nascimento=date(2013, 5, 10),
            turma=coroinha.turma,
            status=coroinha.status,
        )
        escala = EscalaService.montar(
            data=date(2026, 6, 20),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=2,
            usuario=coordenador,
        )
        EscalaService.atribuir_funcoes(
            escala,
            {
                FuncaoEscala.VELA_1.value: coroinha.id,
                FuncaoEscala.VELA_2.value: coroinha2.id,
            },
        )
        funcoes = set(escala.itens.exclude(funcao__isnull=True).values_list("funcao", flat=True))
        assert funcoes == {FuncaoEscala.VELA_1, FuncaoEscala.VELA_2}

    def test_mesmo_coroinha_duas_funcoes_falha(self, coordenador, missa_domingo, coroinha):
        escala = EscalaService.montar(
            data=date(2026, 6, 22),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=1,
            usuario=coordenador,
        )
        with pytest.raises(ValueError, match="duas funções"):
            EscalaService.atribuir_funcoes(
                escala,
                {FuncaoEscala.VELA_1.value: coroinha.id, FuncaoEscala.CRUZ.value: coroinha.id},
            )


class TestEscalaAPI:
    def test_montar_via_api(self, client_coordenador, missa_domingo, coroinha):
        res = client_coordenador.post(
            "/api/v1/escalas/montar/",
            {
                "data": "2026-06-25",
                "missa_id": missa_domingo.id,
                "modo": "SorteioAutomatico",
                "quantidade": 1,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        assert len(res.data["itens"]) == 1

    def test_padre_nao_monta_escala(self, client_padre, missa_domingo):
        res = client_padre.post(
            "/api/v1/escalas/montar/",
            {
                "data": "2026-06-26",
                "missa_id": missa_domingo.id,
                "modo": "SorteioAutomatico",
                "quantidade": 1,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN


class TestRelatorioPDF:
    def test_exportar_pdf_mes(self, coordenador, missa_domingo, coroinha):
        EscalaService.montar(
            data=date(2026, 6, 10),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=1,
            usuario=coordenador,
        )
        pdf = RelatorioEscalaService.exportar_mes_pdf(2026, 6)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_exportar_pdf_via_api(self, client_coordenador, coordenador, missa_domingo, coroinha):
        EscalaService.montar(
            data=date(2026, 7, 5),
            missa_id=missa_domingo.id,
            modo="SorteioAutomatico",
            quantidade=1,
            usuario=coordenador,
        )
        res = client_coordenador.get("/api/v1/relatorios/escala-mes?ano=2026&mes=7&formato=pdf")
        assert res.status_code == status.HTTP_200_OK
        assert res["Content-Type"] == "application/pdf"
        assert res.content[:4] == b"%PDF"

    def test_padre_nao_exporta_pdf(self, client_padre):
        res = client_padre.get("/api/v1/relatorios/escala-mes?ano=2026&mes=7&formato=pdf")
        assert res.status_code == status.HTTP_403_FORBIDDEN
