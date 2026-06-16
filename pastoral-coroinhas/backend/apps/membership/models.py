from django.db import models


class Turma(models.TextChoices):
    INICIANTE = "Iniciante", "Iniciante"
    INTERMEDIARIO = "Intermediario", "Intermediário"
    AVANCADO = "Avancado", "Avançado"


class StatusCoroinha(models.TextChoices):
    ATIVO = "Ativo", "Ativo"
    EM_FORMACAO = "EmFormacao", "Em formação"
    INATIVO = "Inativo", "Inativo"


class StatusInscricao(models.TextChoices):
    PENDENTE = "Pendente", "Pendente"
    APROVADA = "Aprovada", "Aprovada"
    REJEITADA = "Rejeitada", "Rejeitada"


class Responsavel(models.Model):
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=11, unique=True, db_index=True)
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    nome_mae = models.CharField(max_length=200, blank=True)
    nome_pai = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Responsável"
        verbose_name_plural = "Responsáveis"

    def __str__(self):
        return self.nome

    def filhos_ids(self) -> list[int]:
        return list(self.coroinhas.values_list("id", flat=True))


class Coroinha(models.Model):
    nome = models.CharField(max_length=200)
    data_nascimento = models.DateField()
    cpf = models.CharField(max_length=11, blank=True, db_index=True)
    telefone = models.CharField(max_length=20, blank=True)
    endereco = models.TextField(blank=True)
    escola = models.CharField(max_length=200, blank=True)
    serie = models.CharField(max_length=50, blank=True)
    turma = models.CharField(max_length=20, choices=Turma.choices, default=Turma.INICIANTE)
    status = models.CharField(
        max_length=20, choices=StatusCoroinha.choices, default=StatusCoroinha.EM_FORMACAO
    )
    batizado = models.BooleanField(default=False)
    primeira_eucaristia = models.BooleanField(default=False)
    crisma = models.BooleanField(default=False)
    foto = models.ImageField(upload_to="coroinhas/fotos/", blank=True, null=True)
    responsaveis = models.ManyToManyField(Responsavel, related_name="coroinhas", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Coroinha"
        verbose_name_plural = "Coroinhas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    @property
    def idade(self) -> int:
        from datetime import date

        hoje = date.today()
        anos = hoje.year - self.data_nascimento.year
        if (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day):
            anos -= 1
        return anos


class Inscricao(models.Model):
    status = models.CharField(
        max_length=20, choices=StatusInscricao.choices, default=StatusInscricao.PENDENTE
    )
    dados = models.JSONField(default=dict)
    foto_pendente = models.ImageField(upload_to="inscricoes/fotos/", blank=True, null=True)
    coroinha = models.ForeignKey(
        Coroinha, on_delete=models.SET_NULL, null=True, blank=True, related_name="inscricoes"
    )
    responsavel = models.ForeignKey(
        Responsavel, on_delete=models.SET_NULL, null=True, blank=True, related_name="inscricoes"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    aprovado_em = models.DateTimeField(null=True, blank=True)
    aprovado_por = models.ForeignKey(
        "identity.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inscricoes_aprovadas",
    )

    class Meta:
        verbose_name = "Inscrição"
        verbose_name_plural = "Inscrições"
        ordering = ["-criado_em"]

    def __str__(self):
        nome = self.dados.get("coroinha", {}).get("nome", "Sem nome")
        return f"Inscrição {nome} ({self.status})"
