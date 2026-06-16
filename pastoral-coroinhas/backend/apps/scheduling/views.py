from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.permissions import IsGestorCoroinhas, IsStaffPastoral
from apps.scheduling.models import Escala, Missa
from apps.scheduling.serializers import (
    AtribuirFuncoesSerializer,
    EscalaSerializer,
    MissaSerializer,
    MontarEscalaSerializer,
)
from apps.scheduling.services.escala_service import EscalaService
from apps.scheduling.services.relatorio_escala_service import RelatorioEscalaService


class MissaViewSet(viewsets.ModelViewSet):
    queryset = Missa.objects.all()
    serializer_class = MissaSerializer
    permission_classes = [IsStaffPastoral]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsStaffPastoral()]
        return [IsGestorCoroinhas()]


class EscalaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Escala.objects.select_related("missa").prefetch_related("itens__coroinha")
    serializer_class = EscalaSerializer
    permission_classes = [IsStaffPastoral]

    @action(detail=False, methods=["post"], permission_classes=[IsGestorCoroinhas])
    def montar(self, request):
        serializer = MontarEscalaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            escala = EscalaService.montar(
                data=data["data"],
                missa_id=data["missa_id"],
                modo=data["modo"],
                quantidade=data["quantidade"],
                usuario=request.user,
                coroinha_ids=data.get("coroinha_ids"),
                funcoes=data.get("funcoes"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        escala = Escala.objects.prefetch_related("itens__coroinha").get(pk=escala.pk)
        return Response(EscalaSerializer(escala, context={"request": request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="funcoes", permission_classes=[IsGestorCoroinhas])
    def atribuir_funcoes(self, request, pk=None):
        escala = self.get_object()
        serializer = AtribuirFuncoesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            EscalaService.atribuir_funcoes(escala, serializer.validated_data.get("funcoes", {}))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        escala = Escala.objects.prefetch_related("itens__coroinha").get(pk=escala.pk)
        return Response(EscalaSerializer(escala, context={"request": request}).data)


class RelatorioEscalaMesView(APIView):
    permission_classes = [IsGestorCoroinhas]

    def get(self, request):
        hoje = timezone.now().date()
        try:
            mes = int(request.query_params.get("mes", hoje.month))
            ano = int(request.query_params.get("ano", hoje.year))
        except (TypeError, ValueError):
            return Response({"detail": "Mês e ano inválidos."}, status=status.HTTP_400_BAD_REQUEST)

        if not (1 <= mes <= 12):
            return Response({"detail": "Mês deve ser entre 1 e 12."}, status=status.HTTP_400_BAD_REQUEST)

        formato = request.query_params.get("formato", "pdf")
        if formato == "json":
            return Response(RelatorioEscalaService.exportar_mes_json(ano, mes))

        if formato == "csv":
            csv_content = RelatorioEscalaService.exportar_mes_csv(ano, mes)
            response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="escala-{ano}-{mes:02d}.csv"'
            return response

        pdf_bytes = RelatorioEscalaService.exportar_mes_pdf(ano, mes)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="escala-{ano}-{mes:02d}.pdf"'
        return response
