from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.attendance.views import PresencaEscalaView, PresencaResumoView
from apps.communication.views import EnviarMensagemView, MensagemViewSet
from apps.content.views import DocumentoViewSet, NoticiaViewSet
from apps.membership.views import (
    CoroinhaViewSet,
    DashboardStatsView,
    InscricaoPublicaView,
    InscricaoViewSet,
    PortalCoroinhaView,
    PortalFilhosView,
    ProximasEscalasView,
    RelatorioGeralView,
)
from apps.scheduling.views import EscalaViewSet, MissaViewSet, RelatorioEscalaMesView
from apps.training.views import FormacaoViewSet

router = DefaultRouter()
router.register(r"coroinhas", CoroinhaViewSet, basename="coroinha")
router.register(r"inscricoes", InscricaoViewSet, basename="inscricao")
router.register(r"missas", MissaViewSet, basename="missa")
router.register(r"escalas", EscalaViewSet, basename="escala")
router.register(r"formacoes", FormacaoViewSet, basename="formacao")
router.register(r"mensagens", MensagemViewSet, basename="mensagem")
router.register(r"noticias", NoticiaViewSet, basename="noticia")
router.register(r"documentos", DocumentoViewSet, basename="documento")

urlpatterns = [
    path("auth/", include("apps.identity.urls")),
    path("inscricoes/publica", InscricaoPublicaView.as_view(), name="inscricao-publica"),
    path("portal/filhos", PortalFilhosView.as_view(), name="portal-filhos"),
    path("portal/coroinhas/<int:coroinha_id>/resumo", PortalCoroinhaView.as_view(), name="portal-resumo"),
    path("dashboard/stats", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("dashboard/proximas-escalas", ProximasEscalasView.as_view(), name="proximas-escalas"),
    path("relatorios/geral", RelatorioGeralView.as_view(), name="relatorio-geral"),
    path("relatorios/escala-mes", RelatorioEscalaMesView.as_view(), name="relatorio-escala-mes"),
    path("presenca/resumo", PresencaResumoView.as_view(), name="presenca-resumo"),
    path("presenca/escalas/<int:escala_id>", PresencaEscalaView.as_view(), name="presenca-escala"),
    path("mensagens/enviar", EnviarMensagemView.as_view(), name="mensagem-enviar"),
    path("", include(router.urls)),
]
