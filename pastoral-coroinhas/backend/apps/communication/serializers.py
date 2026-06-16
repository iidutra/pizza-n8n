from rest_framework import serializers

from apps.communication.models import CanalMensagem, Mensagem


class MensagemSerializer(serializers.ModelSerializer):
    destinatarios_nomes = serializers.SerializerMethodField()

    class Meta:
        model = Mensagem
        fields = (
            "id",
            "canal",
            "corpo",
            "destinatarios_nomes",
            "enviada_em",
            "simulacao",
        )

    def get_destinatarios_nomes(self, obj):
        return list(obj.destinatarios.values_list("nome", flat=True))


class EnviarMensagemSerializer(serializers.Serializer):
    canal = serializers.ChoiceField(choices=CanalMensagem.choices)
    corpo = serializers.CharField()
    coroinha_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
