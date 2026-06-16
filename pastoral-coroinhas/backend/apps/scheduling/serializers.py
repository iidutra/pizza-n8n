from rest_framework import serializers

from apps.scheduling.models import Escala, EscalaItem, Missa, ModoEscala, FuncaoEscala


class MissaSerializer(serializers.ModelSerializer):
    recorrencia = serializers.CharField(read_only=True)

    class Meta:
        model = Missa
        fields = ("id", "nome", "dia_semana", "dia_mes", "horario", "ativa", "recorrencia")

    def validate(self, attrs):
        dia_semana = attrs.get("dia_semana", getattr(self.instance, "dia_semana", None))
        dia_mes = attrs.get("dia_mes", getattr(self.instance, "dia_mes", None))
        if self.partial:
            if "dia_semana" in attrs and attrs["dia_semana"] and dia_mes:
                attrs["dia_mes"] = None
            if "dia_mes" in attrs and attrs["dia_mes"] and dia_semana:
                attrs["dia_semana"] = None
            dia_semana = attrs.get("dia_semana", getattr(self.instance, "dia_semana", None))
            dia_mes = attrs.get("dia_mes", getattr(self.instance, "dia_mes", None))
        if not dia_semana and not dia_mes:
            raise serializers.ValidationError("Informe o dia da semana ou o dia do mês.")
        if dia_semana and dia_mes:
            raise serializers.ValidationError("Use dia da semana ou dia do mês, não ambos.")
        if dia_mes is not None and not (1 <= dia_mes <= 31):
            raise serializers.ValidationError({"dia_mes": "Dia do mês deve ser entre 1 e 31."})
        return attrs

    def create(self, validated_data):
        if validated_data.get("dia_mes"):
            validated_data["dia_semana"] = None
        else:
            validated_data["dia_mes"] = None
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.get("dia_mes"):
            validated_data["dia_semana"] = None
        elif validated_data.get("dia_semana"):
            validated_data["dia_mes"] = None
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["recorrencia"] = instance.recorrencia
        return data


from apps.membership.utils.media import build_foto_url


class EscalaItemSerializer(serializers.ModelSerializer):
    coroinha_nome = serializers.CharField(source="coroinha.nome", read_only=True)
    coroinha_id = serializers.IntegerField(source="coroinha.id", read_only=True)
    coroinha_foto_url = serializers.SerializerMethodField()
    presenca_status = serializers.SerializerMethodField()
    funcao_label = serializers.SerializerMethodField()

    class Meta:
        model = EscalaItem
        fields = (
            "id",
            "coroinha_id",
            "coroinha_nome",
            "coroinha_foto_url",
            "ordem",
            "funcao",
            "funcao_label",
            "presenca_status",
        )

    def get_funcao_label(self, obj):
        return obj.get_funcao_display() if obj.funcao else None

    def get_coroinha_foto_url(self, obj):
        return build_foto_url(obj.coroinha.foto, self.context.get("request"))

    def get_presenca_status(self, obj):
        try:
            return obj.presenca.status
        except Exception:
            return None


class EscalaSerializer(serializers.ModelSerializer):
    missa_nome = serializers.CharField(source="missa.nome", read_only=True)
    itens = EscalaItemSerializer(many=True, read_only=True)

    class Meta:
        model = Escala
        fields = ("id", "data", "missa", "missa_nome", "modo", "criado_em", "itens")


class MontarEscalaSerializer(serializers.Serializer):
    data = serializers.DateField()
    missa_id = serializers.IntegerField()
    modo = serializers.ChoiceField(choices=ModoEscala.choices)
    quantidade = serializers.IntegerField(min_value=1, max_value=20)
    coroinha_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    funcoes = serializers.DictField(child=serializers.IntegerField(), required=False, allow_empty=True)

    def validate_funcoes(self, value):
        validas = {c.value for c in FuncaoEscala}
        for chave in value:
            if chave not in validas:
                raise serializers.ValidationError(f"Função inválida: {chave}")
        return value

    def validate(self, attrs):
        if attrs["modo"] == ModoEscala.SELECAO_MANUAL and not attrs.get("coroinha_ids"):
            raise serializers.ValidationError({"coroinha_ids": "Obrigatório para seleção manual."})
        return attrs


class AtribuirFuncoesSerializer(serializers.Serializer):
    funcoes = serializers.DictField(child=serializers.IntegerField(allow_null=True), allow_empty=True)

    def validate_funcoes(self, value):
        validas = {c.value for c in FuncaoEscala}
        for chave in value:
            if chave not in validas:
                raise serializers.ValidationError(f"Função inválida: {chave}")
        return value
