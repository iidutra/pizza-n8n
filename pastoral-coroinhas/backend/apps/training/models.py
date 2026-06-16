from django.db import models


class Formacao(models.Model):
    titulo = models.CharField(max_length=200)
    data = models.DateField()
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Formação"
        verbose_name_plural = "Formações"
        ordering = ["-data"]

    def __str__(self):
        return self.titulo


class FormacaoConclusao(models.Model):
    formacao = models.ForeignKey(Formacao, on_delete=models.CASCADE, related_name="conclusoes")
    coroinha = models.ForeignKey(
        "membership.Coroinha", on_delete=models.CASCADE, related_name="formacoes_concluidas"
    )
    concluido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Conclusão de formação"
        unique_together = [("formacao", "coroinha")]

    def __str__(self):
        return f"{self.coroinha.nome} — {self.formacao.titulo}"
