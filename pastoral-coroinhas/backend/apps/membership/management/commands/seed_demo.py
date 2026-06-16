from datetime import date, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.attendance.models import Presenca, StatusPresenca
from apps.content.models import CategoriaDocumento, Documento, Noticia
from apps.identity.models import TipoPerfil, Usuario
from apps.identity.utils.cpf import validar_cpf
from apps.membership.models import Coroinha, Responsavel, StatusCoroinha, Turma
from apps.scheduling.models import Escala, EscalaItem, Missa, ModoEscala
from apps.scheduling.services.escala_service import EscalaService
from apps.training.models import Formacao, FormacaoConclusao

DEMO_SENHA = "demo123"
CPF_PAI = "11144477735"
CPF_COROINHA = "52998224725"


class Command(BaseCommand):
    help = "Popula dados de demonstração (idempotente)."

    def _criar_usuarios_demo(self, responsavel: Responsavel, coroinha_login: Coroinha):
        padre, _ = Usuario.objects.get_or_create(
            email="padre@paroquia.org",
            defaults={
                "nome": "Pe. João Carlos",
                "tipo_perfil": TipoPerfil.PADRE,
            },
        )
        padre.tipo_perfil = TipoPerfil.PADRE
        padre.set_password(DEMO_SENHA)
        padre.must_change_password = False
        padre.save()

        secretario, _ = Usuario.objects.get_or_create(
            email="secretario@paroquia.org",
            defaults={
                "nome": "Maria Secretária",
                "tipo_perfil": TipoPerfil.SECRETARIO,
            },
        )
        secretario.tipo_perfil = TipoPerfil.SECRETARIO
        secretario.set_password(DEMO_SENHA)
        secretario.must_change_password = False
        secretario.save()

        pai, _ = Usuario.objects.get_or_create(
            cpf=responsavel.cpf,
            defaults={
                "nome": responsavel.nome,
                "tipo_perfil": TipoPerfil.PAI,
                "responsavel": responsavel,
            },
        )
        pai.tipo_perfil = TipoPerfil.PAI
        pai.responsavel = responsavel
        pai.set_password(DEMO_SENHA)
        pai.must_change_password = False
        pai.save()

        if coroinha_login.cpf and validar_cpf(coroinha_login.cpf):
            coroinha_user, _ = Usuario.objects.get_or_create(
                cpf=coroinha_login.cpf,
                defaults={
                    "nome": coroinha_login.nome,
                    "tipo_perfil": TipoPerfil.COROINHA,
                    "coroinha": coroinha_login,
                },
            )
            coroinha_user.tipo_perfil = TipoPerfil.COROINHA
            coroinha_user.coroinha = coroinha_login
            coroinha_user.set_password(DEMO_SENHA)
            coroinha_user.must_change_password = False
            coroinha_user.save()

        self.stdout.write(self.style.SUCCESS("Usuários demo:"))
        self.stdout.write(f"  Padre (staff): padre@paroquia.org / {DEMO_SENHA}")
        self.stdout.write(f"  Secretário (staff): secretario@paroquia.org / {DEMO_SENHA}")
        self.stdout.write(f"  Pai (família): {CPF_PAI} / {DEMO_SENHA}")
        self.stdout.write(f"  Coroinha (família): {CPF_COROINHA} / {DEMO_SENHA}")

    def handle(self, *args, **options):
        call_command("setup_missas")

        demo = [
            ("João Pedro Silva", date(2012, 3, 15), Turma.INTERMEDIARIO, StatusCoroinha.ATIVO, "Colégio São José", "7º ano"),
            ("Maria Eduarda Santos", date(2014, 7, 22), Turma.INICIANTE, StatusCoroinha.ATIVO, "Escola Santa Maria", "5º ano"),
            ("Pedro Henrique Lima", date(2012, 1, 10), Turma.AVANCADO, StatusCoroinha.ATIVO, "Colégio São José", "8º ano"),
            ("Lucas Almeida", date(2014, 11, 5), Turma.INICIANTE, StatusCoroinha.EM_FORMACAO, "Escola Paroquial", "5º ano"),
            ("Ana Clara Ferreira", date(2013, 6, 18), Turma.INTERMEDIARIO, StatusCoroinha.ATIVO, "Colégio São José", "6º ano"),
        ]

        coroinhas = []
        for i, (nome, nasc, turma, status, escola, serie) in enumerate(demo):
            defaults = {
                "data_nascimento": nasc,
                "turma": turma,
                "status": status,
                "escola": escola,
                "serie": serie,
                "batizado": True,
                "primeira_eucaristia": True,
            }
            if i == 0:
                defaults["cpf"] = CPF_COROINHA
            c, _ = Coroinha.objects.get_or_create(nome=nome, defaults=defaults)
            if i == 0 and c.cpf != CPF_COROINHA:
                c.cpf = CPF_COROINHA
                c.save(update_fields=["cpf"])
            coroinhas.append(c)

        resp, _ = Responsavel.objects.get_or_create(
            cpf=CPF_PAI,
            defaults={
                "nome": "Maria Silva",
                "nome_mae": "Maria Silva",
                "telefone": "11999990000",
                "whatsapp": "11999990000",
                "email": "maria@email.com",
            },
        )
        for c in coroinhas[:2]:
            resp.coroinhas.add(c)

        hoje = timezone.now().date()
        missa_dom = Missa.objects.filter(nome="Domingo 18h30").first()
        missa_dia13 = Missa.objects.filter(nome="Dia 13 — 18h").first()

        if missa_dom:
            data_dom = hoje + timedelta(days=(6 - hoje.weekday()) % 7 or 7)
            escala_dom, created = Escala.objects.get_or_create(
                data=data_dom,
                missa=missa_dom,
                defaults={"modo": ModoEscala.SORTEIO_AUTOMATICO},
            )
            if created:
                for i, c in enumerate(coroinhas[:3]):
                    EscalaItem.objects.get_or_create(escala=escala_dom, coroinha=c, defaults={"ordem": i})
                for item in escala_dom.itens.all()[:2]:
                    Presenca.objects.get_or_create(
                        escala_item=item,
                        defaults={"status": StatusPresenca.PRESENTE},
                    )

        if missa_dia13:
            dia13 = hoje.replace(day=13)
            if dia13 < hoje:
                if hoje.month == 12:
                    dia13 = dia13.replace(year=hoje.year + 1, month=1)
                else:
                    dia13 = dia13.replace(month=hoje.month + 1)
            try:
                EscalaService.montar(
                    data=dia13,
                    missa_id=missa_dia13.id,
                    modo=ModoEscala.SORTEIO_AUTOMATICO,
                    quantidade=2,
                    usuario=None,
                )
            except ValueError:
                pass

        formacoes_data = [
            ("Formação 01 — História da Missa", hoje - timedelta(days=40), "Origens e evolução da celebração eucarística."),
            ("Formação 02 — Objetos Litúrgicos", hoje - timedelta(days=26), "Cálice, patena, âmbula, turíbulo e suas funções."),
            ("Formação 03 — Ano Litúrgico", hoje - timedelta(days=12), "Tempos litúrgicos, cores e símbolos."),
        ]
        for titulo, data_f, desc in formacoes_data:
            f, _ = Formacao.objects.get_or_create(titulo=titulo, defaults={"data": data_f, "descricao": desc})
            for c in coroinhas[:3] if "01" in titulo or "02" in titulo else []:
                FormacaoConclusao.objects.get_or_create(formacao=f, coroinha=c)

        noticias_data = [
            (
                "Festa de São Tarcísio — Padroeiro dos Coroinhas",
                "No dia 15 de agosto celebraremos solenemente São Tarcísio. Todos os coroinhas servirão na missa das 19h.",
                True,
            ),
            (
                "Encontro de Formação no próximo sábado",
                "Convidamos todos os coroinhas para o encontro de formação no sábado, às 15h, no salão paroquial.",
                False,
            ),
            (
                "Inscrições abertas para novos coroinhas",
                "As inscrições para a nova turma estão abertas. Preencha o formulário online.",
                False,
            ),
        ]
        for titulo, conteudo, destaque in noticias_data:
            Noticia.objects.get_or_create(titulo=titulo, defaults={"conteudo": conteudo, "destaque": destaque, "ativo": True})

        docs_data = [
            ("Paramentos Litúrgicos: O Pálio", "Vestes e símbolos sagrados.", CategoriaDocumento.LITURGIA),
            ("A Santa Missa (parte por parte)", "Participação consciente em cada momento.", CategoriaDocumento.FORMACAO),
            ("Ritual de Admissão de Coroinhas", "Ser coroinha é consagrar a vida a Deus.", CategoriaDocumento.RITUAL),
        ]
        for titulo, desc, cat in docs_data:
            Documento.objects.get_or_create(titulo=titulo, defaults={"descricao": desc, "categoria": cat, "ativo": True})

        self._criar_usuarios_demo(resp, coroinhas[0])

        self.stdout.write(self.style.SUCCESS(f"Demo: {len(coroinhas)} coroinhas, missas, escalas, formações, notícias e documentos."))