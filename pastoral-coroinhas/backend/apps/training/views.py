from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.identity.permissions import IsGestorCoroinhas, IsStaffPastoral
from apps.training.models import Formacao, FormacaoConclusao
from apps.training.serializers import (
    FormacaoConclusaoSerializer,
    FormacaoSerializer,
    ToggleConclusaoSerializer,
)


class FormacaoViewSet(viewsets.ModelViewSet):
    queryset = Formacao.objects.all()
    serializer_class = FormacaoSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "conclusoes"):
            return [IsStaffPastoral()]
        return [IsGestorCoroinhas()]

    @action(detail=True, methods=["get"])
    def conclusoes(self, request, pk=None):
        formacao = self.get_object()
        qs = FormacaoConclusao.objects.filter(formacao=formacao).select_related("coroinha")
        from apps.membership.models import Coroinha

        concluidos = {c.coroinha_id for c in qs}
        coroinhas = Coroinha.objects.filter(
            status__in=["Ativo", "EmFormacao"]
        ).order_by("nome")
        data = [
            {
                "coroinha_id": c.id,
                "coroinha_nome": c.nome,
                "concluido": c.id in concluidos,
            }
            for c in coroinhas
        ]
        return Response(data)

    @action(detail=True, methods=["post"])
    def toggle_conclusao(self, request, pk=None):
        formacao = self.get_object()
        serializer = ToggleConclusaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cid = serializer.validated_data["coroinha_id"]
        if serializer.validated_data["concluido"]:
            FormacaoConclusao.objects.get_or_create(formacao=formacao, coroinha_id=cid)
        else:
            FormacaoConclusao.objects.filter(formacao=formacao, coroinha_id=cid).delete()
        return Response({"ok": True})
