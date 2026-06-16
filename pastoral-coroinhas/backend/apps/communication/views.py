from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.models import Mensagem
from apps.communication.serializers import EnviarMensagemSerializer, MensagemSerializer
from apps.communication.services.comunicacao_service import ComunicacaoService
from apps.identity.permissions import IsGestorCoroinhas, IsStaffPastoral


class MensagemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Mensagem.objects.prefetch_related("destinatarios").all()
    serializer_class = MensagemSerializer
    permission_classes = [IsStaffPastoral]


class EnviarMensagemView(APIView):
    permission_classes = [IsGestorCoroinhas]

    def post(self, request):
        serializer = EnviarMensagemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            msg = ComunicacaoService.enviar(
                canal=data["canal"],
                corpo=data["corpo"],
                coroinha_ids=data["coroinha_ids"],
                usuario=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(MensagemSerializer(msg).data, status=status.HTTP_201_CREATED)
