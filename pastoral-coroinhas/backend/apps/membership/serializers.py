from rest_framework import serializers

from apps.membership.models import Coroinha, Inscricao, StatusCoroinha, Turma
from apps.membership.utils.media import build_foto_url


class CoroinhaSerializer(serializers.ModelSerializer):
    idade = serializers.IntegerField(read_only=True)
    foto_url = serializers.SerializerMethodField()

    class Meta:
        model = Coroinha
        fields = (
            "id",
            "nome",
            "data_nascimento",
            "idade",
            "cpf",
            "telefone",
            "endereco",
            "escola",
            "serie",
            "turma",
            "status",
            "batizado",
            "primeira_eucaristia",
            "crisma",
            "foto_url",
            "criado_em",
        )

    def get_foto_url(self, obj):
        return build_foto_url(obj.foto, self.context.get("request"))


class InscricaoPublicaSerializer(serializers.Serializer):
    coroinha = serializers.DictField()
    responsavel = serializers.DictField()

    def validate_coroinha(self, value):
        if not value.get("nome"):
            raise serializers.ValidationError("Nome do coroinha é obrigatório.")
        if not value.get("data_nascimento"):
            raise serializers.ValidationError("Data de nascimento é obrigatória.")
        turma = value.get("turma", Turma.INICIANTE)
        if turma not in dict(Turma.choices):
            value["turma"] = Turma.INICIANTE
        return value

    def validate_responsavel(self, value):
        if not value.get("cpf"):
            raise serializers.ValidationError("CPF do responsável é obrigatório.")
        return value


class InscricaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inscricao
        fields = ("id", "status", "dados", "criado_em", "aprovado_em", "coroinha", "responsavel")
        read_only_fields = fields


class CoroinhaResumoPortalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nome = serializers.CharField()
    idade = serializers.IntegerField()
    escola = serializers.CharField()
    serie = serializers.CharField()
    turma = serializers.CharField()
    status = serializers.CharField()
    foto_url = serializers.CharField(allow_null=True, required=False)
    escalas_total = serializers.IntegerField()
    presencas_total = serializers.IntegerField()
    faltas_total = serializers.IntegerField()
    formacoes_concluidas = serializers.IntegerField()
    formacoes_total = serializers.IntegerField(required=False)
    proxima_escala = serializers.JSONField(allow_null=True)
    escalas = serializers.ListField()
    formacoes = serializers.ListField()


class AniversarianteSerializer(serializers.ModelSerializer):
    idade = serializers.IntegerField(read_only=True)
    foto_url = serializers.SerializerMethodField()
    dia = serializers.SerializerMethodField()

    class Meta:
        model = Coroinha
        fields = ("id", "nome", "data_nascimento", "idade", "dia", "foto_url", "turma")

    def get_foto_url(self, obj):
        return build_foto_url(obj.foto, self.context.get("request"))

    def get_dia(self, obj):
        return obj.data_nascimento.day
