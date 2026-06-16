import pytest
from rest_framework import status

from apps.identity.services.auth_service import AuthService

pytestmark = pytest.mark.django_db


class TestAuthService:
    def test_login_staff_por_email(self, coordenador):
        user = AuthService.login("coord@test.org", "teste123")
        assert user.id == coordenador.id

    def test_login_familia_por_cpf(self, usuario_pai):
        user = AuthService.login("111.444.777-35", "teste123")
        assert user.id == usuario_pai.id

    def test_login_senha_invalida(self, coordenador):
        with pytest.raises(ValueError, match="Credenciais inválidas"):
            AuthService.login("coord@test.org", "errada")


class TestLoginAPI:
    def test_login_unificado_email(self, api_client, coordenador):
        res = api_client.post(
            "/api/v1/auth/login",
            {"identificador": "coord@test.org", "senha": "teste123"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK
        assert "access" in res.data
        assert res.data["usuario"]["tipo_perfil"] == "Coordenador"

    def test_login_unificado_cpf(self, api_client, usuario_pai):
        res = api_client.post(
            "/api/v1/auth/login",
            {"identificador": "111.444.777-35", "senha": "teste123"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.data["usuario"]["tipo_perfil"] == "Pai"

    def test_login_sem_credenciais(self, api_client):
        res = api_client.post(
            "/api/v1/auth/login",
            {"identificador": "coord@test.org", "senha": "errada"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
