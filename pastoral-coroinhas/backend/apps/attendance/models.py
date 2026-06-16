from django.db import models


class StatusPresenca(models.TextChoices):
    PRESENTE = "Presente", "Presente"
    AUSENTE = "Ausente", "Ausente"


class Presenca(models.Model):
    escala_item = models.OneToOneField(
        "scheduling.EscalaItem",
        on_delete=models.CASCADE,
        related_name="presenca",
    )
    status = models.CharField(max_length=20, choices=StatusPresenca.choices)
    registrado_em = models.DateTimeField(auto_now=True)
    registrado_por = models.ForeignKey(
        "identity.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        related_name="presencas_registradas",
    )

    class Meta:
        verbose_name = "Presença"
        verbose_name_plural = "Presenças"

    def __str__(self):
        return f"{self.escala_item.coroinha.nome} — {self.status}"
