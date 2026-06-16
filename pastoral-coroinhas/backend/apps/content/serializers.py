from rest_framework import serializers

from apps.content.models import Documento, Noticia


class NoticiaSerializer(serializers.ModelSerializer):
    autor_nome = serializers.CharField(source="autor.nome", read_only=True, default="")

    class Meta:
        model = Noticia
        fields = ("id", "titulo", "conteudo", "destaque", "publicado_em", "ativo", "autor_nome")


class DocumentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documento
        fields = ("id", "titulo", "descricao", "url", "categoria", "ativo", "criado_em")
