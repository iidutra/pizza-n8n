from django.utils import timezone

from apps.attendance.models import Presenca, StatusPresenca
from apps.identity.models import TipoPerfil, Usuario
from apps.scheduling.models import Escala, EscalaItem
from apps.training.models import Formacao, FormacaoConclusao


from apps.membership.utils.media import build_foto_url


class PortalService:
    @staticmethod
    def pode_ver_coroinha(usuario: Usuario, coroinha_id: int) -> bool:
        if usuario.tipo_perfil == TipoPerfil.COROINHA:
            return usuario.coroinha_id == coroinha_id
        if usuario.tipo_perfil == TipoPerfil.PAI:
            return (
                usuario.responsavel is not None
                and usuario.responsavel.coroinhas.filter(id=coroinha_id).exists()
            )
        return False

    @staticmethod
    def coroinhas_acessiveis(usuario: Usuario):
        from apps.membership.models import Coroinha

        if usuario.tipo_perfil == TipoPerfil.COROINHA and usuario.coroinha_id:
            return Coroinha.objects.filter(id=usuario.coroinha_id)
        if usuario.tipo_perfil == TipoPerfil.PAI and usuario.responsavel_id:
            return usuario.responsavel.coroinhas.all()
        return Coroinha.objects.none()

    @classmethod
    def get_resumo(cls, usuario: Usuario, coroinha_id: int, request=None) -> dict:
        if not cls.pode_ver_coroinha(usuario, coroinha_id):
            raise PermissionError("Sem permissão para ver este coroinha.")

        from apps.membership.models import Coroinha

        coroinha = Coroinha.objects.get(id=coroinha_id)
        hoje = timezone.now().date()

        itens = EscalaItem.objects.filter(coroinha=coroinha).select_related(
            "escala", "escala__missa"
        )
        escalas_total = itens.count()
        presencas_total = Presenca.objects.filter(
            escala_item__in=itens, status=StatusPresenca.PRESENTE
        ).count()
        faltas_total = Presenca.objects.filter(
            escala_item__in=itens, status=StatusPresenca.AUSENTE
        ).count()

        conclusoes = FormacaoConclusao.objects.filter(coroinha=coroinha).select_related("formacao")
        formacoes_concluidas = conclusoes.count()

        proxima_item = (
            itens.filter(escala__data__gte=hoje).order_by("escala__data", "escala__missa__horario").first()
        )
        proxima_escala = None
        if proxima_item:
            proxima_escala = {
                "data": proxima_item.escala.data.isoformat(),
                "missa": proxima_item.escala.missa.nome,
            }

        escalas_list = []
        for item in itens.order_by("-escala__data")[:10]:
            pres = getattr(item, "presenca", None)
            try:
                pres = item.presenca
            except Presenca.DoesNotExist:
                pres = None
            escalas_list.append(
                {
                    "data": item.escala.data.isoformat(),
                    "missa": item.escala.missa.nome,
                    "presenca": pres.status if pres else None,
                }
            )

        formacoes_list = [
            {
                "titulo": c.formacao.titulo,
                "data": c.formacao.data.isoformat(),
                "descricao": c.formacao.descricao,
            }
            for c in conclusoes.order_by("-formacao__data")
        ]

        formacoes_total = Formacao.objects.count()

        return {
            "id": coroinha.id,
            "nome": coroinha.nome,
            "idade": coroinha.idade,
            "escola": coroinha.escola,
            "serie": coroinha.serie,
            "turma": coroinha.turma,
            "status": coroinha.status,
            "foto_url": build_foto_url(coroinha.foto, request),
            "escalas_total": escalas_total,
            "presencas_total": presencas_total,
            "faltas_total": faltas_total,
            "formacoes_concluidas": formacoes_concluidas,
            "formacoes_total": formacoes_total,
            "proxima_escala": proxima_escala,
            "escalas": escalas_list,
            "formacoes": formacoes_list,
        }

    @staticmethod
    def proximas_escalas_dashboard(limit: int = 5):
        hoje = timezone.now().date()
        escalas = (
            Escala.objects.filter(data__gte=hoje)
            .select_related("missa")
            .prefetch_related("itens")
            .order_by("data", "missa__horario")[:limit]
        )
        return [
            {
                "id": e.id,
                "data": e.data.isoformat(),
                "missa": e.missa.nome,
                "coroinhas_count": e.itens.count(),
            }
            for e in escalas
        ]
