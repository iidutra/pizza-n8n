from rest_framework import serializers

from apps.training.models import Formacao, FormacaoConclusao


class FormacaoSerializer(serializers.ModelSerializer):
    concluintes_count = serializers.SerializerMethodField()
    coroinha_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Formacao
        fields = ("id", "titulo", "data", "descricao", "criado_em", "concluintes_count", "coroinha_ids")

    def get_concluintes_count(self, obj):
        return obj.conclusoes.count()

    def create(self, validated_data):
        coroinha_ids = validated_data.pop("coroinha_ids", [])
        formacao = Formacao.objects.create(**validated_data)
        for cid in coroinha_ids:
            FormacaoConclusao.objects.get_or_create(formacao=formacao, coroinha_id=cid)
        return formacao


class FormacaoConclusaoSerializer(serializers.ModelSerializer):
    coroinha_nome = serializers.CharField(source="coroinha.nome", read_only=True)

    class Meta:
        model = FormacaoConclusao
        fields = ("id", "formacao", "coroinha", "coroinha_nome", "concluido_em")


class ToggleConclusaoSerializer(serializers.Serializer):
    coroinha_id = serializers.IntegerField()
    concluido = serializers.BooleanField()
