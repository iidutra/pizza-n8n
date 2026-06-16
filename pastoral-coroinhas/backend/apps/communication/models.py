from django.db import models


class CanalMensagem(models.TextChoices):
    WHATSAPP = "WhatsApp", "WhatsApp"
    EMAIL = "Email", "E-mail"


class Mensagem(models.Model):
    canal = models.CharField(max_length=20, choices=CanalMensagem.choices)
    corpo = models.TextField()
    destinatarios = models.ManyToManyField("membership.Coroinha", related_name="mensagens")
    enviada_em = models.DateTimeField(auto_now_add=True)
    enviada_por = models.ForeignKey(
        "identity.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        related_name="mensagens_enviadas",
    )
    simulacao = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Mensagem"
        verbose_name_plural = "Mensagens"
        ordering = ["-enviada_em"]

    def __str__(self):
        return f"{self.canal} — {self.enviada_em:%d/%m/%Y %H:%M}"
