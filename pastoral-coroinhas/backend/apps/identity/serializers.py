from rest_framework import serializers

from apps.identity.models import Usuario
from apps.identity.utils.cpf import mascarar_cpf


class UsuarioSerializer(serializers.ModelSerializer):
    cpf_mascarado = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = (
            "id",
            "nome",
            "email",
            "cpf_mascarado",
            "tipo_perfil",
            "must_change_password",
            "coroinha_id",
            "responsavel_id",
        )

    def get_cpf_mascarado(self, obj):
        return mascarar_cpf(obj.cpf) if obj.cpf else None


class LoginSerializer(serializers.Serializer):
    identificador = serializers.CharField(max_length=200)
    senha = serializers.CharField(write_only=True)


class LoginFamiliaSerializer(serializers.Serializer):
    cpf = serializers.CharField(max_length=14)
    senha = serializers.CharField(write_only=True)


class LoginStaffSerializer(serializers.Serializer):
    email = serializers.EmailField()
    senha = serializers.CharField(write_only=True)


class RecuperarSenhaSerializer(serializers.Serializer):
    cpf = serializers.CharField(max_length=14)
    data_nascimento = serializers.DateField()
    nova_senha = serializers.CharField(min_length=6, write_only=True)
    confirmar_senha = serializers.CharField(min_length=6, write_only=True)

    def validate(self, attrs):
        if attrs["nova_senha"] != attrs["confirmar_senha"]:
            raise serializers.ValidationError({"confirmar_senha": "As senhas não coincidem."})
        return attrs


class TrocarSenhaSerializer(serializers.Serializer):
    senha_atual = serializers.CharField(write_only=True)
    nova_senha = serializers.CharField(min_length=6, write_only=True)
    confirmar_senha = serializers.CharField(min_length=6, write_only=True)

    def validate(self, attrs):
        if attrs["nova_senha"] != attrs["confirmar_senha"]:
            raise serializers.ValidationError({"confirmar_senha": "As senhas não coincidem."})
        return attrs
