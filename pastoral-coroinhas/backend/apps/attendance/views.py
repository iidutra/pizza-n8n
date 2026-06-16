from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.models import Presenca, StatusPresenca
from apps.identity.permissions import IsGestorCoroinhas, IsStaffPastoral
from apps.scheduling.models import Escala, EscalaItem


class PresencaEscalaView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsStaffPastoral()]
        return [IsGestorCoroinhas()]

    def get(self, request, escala_id):
        try:
            escala = Escala.objects.prefetch_related("itens__coroinha", "itens__presenca").get(pk=escala_id)
        except Escala.DoesNotExist:
            return Response({"detail": "Escala não encontrada."}, status=status.HTTP_404_NOT_FOUND)

        itens = []
        for item in escala.itens.all():
            try:
                pres = item.presenca
                status_val = pres.status
            except Presenca.DoesNotExist:
                status_val = None
            itens.append(
                {
                    "item_id": item.id,
                    "coroinha_id": item.coroinha_id,
                    "coroinha_nome": item.coroinha.nome,
                    "status": status_val,
                }
            )
        return Response(
            {
                "escala_id": escala.id,
                "data": escala.data.isoformat(),
                "missa": escala.missa.nome,
                "itens": itens,
            }
        )

    def patch(self, request, escala_id):
        item_id = request.data.get("item_id")
        novo_status = request.data.get("status")
        if novo_status not in (StatusPresenca.PRESENTE, StatusPresenca.AUSENTE):
            return Response({"detail": "Status inválido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            item = EscalaItem.objects.get(pk=item_id, escala_id=escala_id)
        except EscalaItem.DoesNotExist:
            return Response({"detail": "Item não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        pres, _ = Presenca.objects.update_or_create(
            escala_item=item,
            defaults={"status": novo_status, "registrado_por": request.user},
        )
        return Response({"item_id": item.id, "status": pres.status})


class PresencaResumoView(APIView):
    permission_classes = [IsStaffPastoral]

    def get(self, request):
        from apps.membership.services.relatorio_service import RelatorioService

        return Response(RelatorioService.resumo_presenca_coroinhas())
