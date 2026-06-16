import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestAniversariantes:
    def test_aniversariantes_do_mes(self, client_coordenador, coroinha):
        mes = coroinha.data_nascimento.month
        res = client_coordenador.get(f"/api/v1/coroinhas/aniversariantes/?mes={mes}")
        assert res.status_code == status.HTTP_200_OK
        nomes = [a["nome"] for a in res.data]
        assert coroinha.nome in nomes

    def test_aniversariantes_mes_sem_celebrantes(self, client_coordenador, coroinha):
        mes = 12 if coroinha.data_nascimento.month != 12 else 1
        res = client_coordenador.get(f"/api/v1/coroinhas/aniversariantes/?mes={mes}")
        assert res.status_code == status.HTTP_200_OK
        nomes = [a["nome"] for a in res.data]
        if mes != coroinha.data_nascimento.month:
            assert coroinha.nome not in nomes
