from django.db import transaction

from apps.identity.models import TipoPerfil, Usuario
from apps.identity.utils.cpf import normalizar_cpf, senha_inicial_cpf, validar_cpf
from apps.membership.models import (
    Coroinha,
    Inscricao,
    Responsavel,
    StatusCoroinha,
    StatusInscricao,
    Turma,
)


class InscricaoService:
    @staticmethod
    @transaction.atomic
    def criar_publica(dados: dict, foto=None) -> Inscricao:
        coroinha_data = dados.get("coroinha", {})
        responsavel_data = dados.get("responsavel", {})

        cpf_responsavel = normalizar_cpf(responsavel_data.get("cpf", ""))
        if not validar_cpf(cpf_responsavel):
            raise ValueError("CPF do responsável inválido.")

        if not coroinha_data.get("nome") or not coroinha_data.get("data_nascimento"):
            raise ValueError("Nome e data de nascimento do coroinha são obrigatórios.")

        inscricao = Inscricao.objects.create(dados=dados)
        if foto:
            inscricao.foto_pendente = foto
            inscricao.save(update_fields=["foto_pendente"])
        return inscricao

    @staticmethod
    @transaction.atomic
    def aprovar(inscricao: Inscricao, aprovador: Usuario) -> Coroinha:
        if inscricao.status != StatusInscricao.PENDENTE:
            raise ValueError("Inscrição já foi processada.")

        dados = inscricao.dados
        coroinha_data = dados.get("coroinha", {})
        responsavel_data = dados.get("responsavel", {})

        cpf_responsavel = normalizar_cpf(responsavel_data.get("cpf", ""))
        cpf_coroinha = normalizar_cpf(coroinha_data.get("cpf", ""))

        responsavel, _ = Responsavel.objects.update_or_create(
            cpf=cpf_responsavel,
            defaults={
                "nome": responsavel_data.get("nome_mae") or responsavel_data.get("nome_pai") or "Responsável",
                "telefone": responsavel_data.get("telefone_principal", ""),
                "whatsapp": responsavel_data.get("whatsapp", ""),
                "email": responsavel_data.get("email", ""),
                "nome_mae": responsavel_data.get("nome_mae", ""),
                "nome_pai": responsavel_data.get("nome_pai", ""),
            },
        )

        coroinha = Coroinha.objects.create(
            nome=coroinha_data["nome"],
            data_nascimento=coroinha_data["data_nascimento"],
            cpf=cpf_coroinha,
            telefone=coroinha_data.get("telefone", ""),
            endereco=coroinha_data.get("endereco", ""),
            escola=coroinha_data.get("escola", ""),
            serie=coroinha_data.get("serie", ""),
            turma=coroinha_data.get("turma", Turma.INICIANTE),
            status=StatusCoroinha.EM_FORMACAO,
            batizado=coroinha_data.get("batizado", False),
            primeira_eucaristia=coroinha_data.get("primeira_eucaristia", False),
            crisma=coroinha_data.get("crisma", False),
        )
        coroinha.responsaveis.add(responsavel)

        if inscricao.foto_pendente:
            from django.core.files.base import ContentFile

            coroinha.foto.save(
                inscricao.foto_pendente.name.rsplit("/", 1)[-1],
                ContentFile(inscricao.foto_pendente.read()),
                save=True,
            )

        if not Usuario.objects.filter(cpf=cpf_responsavel).exists():
            Usuario.objects.create_user(
                cpf=cpf_responsavel,
                nome=responsavel.nome,
                tipo_perfil=TipoPerfil.PAI,
                responsavel=responsavel,
                password=senha_inicial_cpf(cpf_responsavel),
                must_change_password=True,
            )

        if cpf_coroinha and validar_cpf(cpf_coroinha) and not Usuario.objects.filter(cpf=cpf_coroinha).exists():
            Usuario.objects.create_user(
                cpf=cpf_coroinha,
                nome=coroinha.nome,
                tipo_perfil=TipoPerfil.COROINHA,
                coroinha=coroinha,
                password=senha_inicial_cpf(cpf_coroinha),
                must_change_password=True,
            )

        from django.utils import timezone

        inscricao.status = StatusInscricao.APROVADA
        inscricao.coroinha = coroinha
        inscricao.responsavel = responsavel
        inscricao.aprovado_em = timezone.now()
        inscricao.aprovado_por = aprovador
        inscricao.save()

        return coroinha

    @staticmethod
    def rejeitar(inscricao: Inscricao) -> None:
        if inscricao.status != StatusInscricao.PENDENTE:
            raise ValueError("Inscrição já foi processada.")
        inscricao.status = StatusInscricao.REJEITADA
        inscricao.save(update_fields=["status"])
