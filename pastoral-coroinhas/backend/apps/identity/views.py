from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.identity.serializers import (
    LoginFamiliaSerializer,
    LoginSerializer,
    LoginStaffSerializer,
    RecuperarSenhaSerializer,
    TrocarSenhaSerializer,
    UsuarioSerializer,
)
from apps.identity.services.auth_service import AuthService


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _token_response(usuario):
    refresh = RefreshToken.for_user(usuario)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "usuario": UsuarioSerializer(usuario).data,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            usuario = AuthService.login(
                identificador=serializer.validated_data["identificador"],
                senha=serializer.validated_data["senha"],
                ip=_client_ip(request),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_token_response(usuario))


class LoginFamiliaView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginFamiliaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            usuario = AuthService.login_familia(
                cpf=serializer.validated_data["cpf"],
                senha=serializer.validated_data["senha"],
                ip=_client_ip(request),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_token_response(usuario))


class LoginStaffView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            usuario = AuthService.login_staff(
                email=serializer.validated_data["email"],
                senha=serializer.validated_data["senha"],
                ip=_client_ip(request),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_token_response(usuario))


class RecuperarSenhaView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RecuperarSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AuthService.recuperar_senha(
                cpf=serializer.validated_data["cpf"],
                data_nascimento=serializer.validated_data["data_nascimento"],
                nova_senha=serializer.validated_data["nova_senha"],
                ip=_client_ip(request),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Senha alterada com sucesso."})


class TrocarSenhaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TrocarSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            AuthService.trocar_senha(
                usuario=request.user,
                senha_atual=serializer.validated_data["senha_atual"],
                nova_senha=serializer.validated_data["nova_senha"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Senha alterada com sucesso."})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)
