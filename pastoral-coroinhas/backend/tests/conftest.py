from datetime import date, time

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.identity.models import TipoPerfil, Usuario
from apps.membership.models import Coroinha, Responsavel, StatusCoroinha, Turma
from apps.scheduling.models import DiaSemana, Missa

SENHA = "teste123"
CPF_PAI = "11144477735"
CPF_COROINHA = "52998224725"


@pytest.fixture
def api_client():
    return APIClient()


def _jwt_client(api_client: APIClient, usuario: Usuario) -> APIClient:
    token = RefreshToken.for_user(usuario)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client


@pytest.fixture
def coordenador(db):
    user = Usuario.objects.create_user(
        email="coord@test.org",
        nome="Coordenador Teste",
        tipo_perfil=TipoPerfil.COORDENADOR,
        password=SENHA,
    )
    return user


@pytest.fixture
def secretario(db):
    return Usuario.objects.create_user(
        email="sec@test.org",
        nome="Secretário Teste",
        tipo_perfil=TipoPerfil.SECRETARIO,
        password=SENHA,
    )


@pytest.fixture
def padre(db):
    return Usuario.objects.create_user(
        email="padre@test.org",
        nome="Padre Teste",
        tipo_perfil=TipoPerfil.PADRE,
        password=SENHA,
    )


@pytest.fixture
def responsavel(db):
    return Responsavel.objects.create(
        nome="Pai Teste",
        cpf=CPF_PAI,
        nome_mae="Mãe Teste",
    )


@pytest.fixture
def coroinha(db, responsavel):
    c = Coroinha.objects.create(
        nome="João Teste",
        data_nascimento=date(2012, 3, 15),
        cpf=CPF_COROINHA,
        turma=Turma.INTERMEDIARIO,
        status=StatusCoroinha.ATIVO,
    )
    c.responsaveis.add(responsavel)
    return c


@pytest.fixture
def usuario_pai(db, responsavel):
    return Usuario.objects.create_user(
        cpf=CPF_PAI,
        nome="Pai Teste",
        tipo_perfil=TipoPerfil.PAI,
        responsavel=responsavel,
        password=SENHA,
    )


@pytest.fixture
def usuario_coroinha(db, coroinha):
    return Usuario.objects.create_user(
        cpf=CPF_COROINHA,
        nome=coroinha.nome,
        tipo_perfil=TipoPerfil.COROINHA,
        coroinha=coroinha,
        password=SENHA,
    )


@pytest.fixture
def missa_domingo(db):
    return Missa.objects.create(
        nome="Domingo 08h",
        dia_semana=DiaSemana.DOMINGO,
        horario=time(8, 0),
        ativa=True,
    )


@pytest.fixture
def client_coordenador(api_client, coordenador):
    return _jwt_client(api_client, coordenador)


@pytest.fixture
def client_padre(api_client, padre):
    return _jwt_client(api_client, padre)


@pytest.fixture
def client_pai(api_client, usuario_pai):
    return _jwt_client(api_client, usuario_pai)
