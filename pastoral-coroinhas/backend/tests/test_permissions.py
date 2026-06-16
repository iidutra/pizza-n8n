import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestPermissoesCoroinha:
    def test_padre_lista_coroinhas(self, client_padre, coroinha):
        res = client_padre.get("/api/v1/coroinhas/")
        assert res.status_code == status.HTTP_200_OK

    def test_padre_nao_envia_foto(self, client_padre, coroinha):
        foto = SimpleUploadedFile("f.jpg", b"fake-image", content_type="image/jpeg")
        res = client_padre.post(
            f"/api/v1/coroinhas/{coroinha.id}/foto/",
            {"foto": foto},
            format="multipart",
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_coordenador_envia_foto(self, client_coordenador, coroinha):
        foto = SimpleUploadedFile("f.jpg", b"fake-image", content_type="image/jpeg")
        res = client_coordenador.post(
            f"/api/v1/coroinhas/{coroinha.id}/foto/",
            {"foto": foto},
            format="multipart",
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.data.get("foto_url")


class TestPortal:
    def test_pai_acessa_portal_filhos(self, client_pai, coroinha):
        res = client_pai.get("/api/v1/portal/filhos")
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data) >= 1

    def test_coordenador_nao_acessa_portal_filhos(self, client_coordenador):
        res = client_coordenador.get("/api/v1/portal/filhos")
        assert res.status_code == status.HTTP_403_FORBIDDEN
