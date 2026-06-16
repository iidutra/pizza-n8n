from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class TipoPerfil(models.TextChoices):
    COORDENADOR = "Coordenador", "Coordenador"
    SECRETARIO = "Secretario", "Secretário"
    PADRE = "Padre", "Padre"
    PAI = "Pai", "Pai"
    COROINHA = "Coroinha", "Coroinha"


class UsuarioManager(BaseUserManager):
    def create_user(self, email=None, cpf=None, password=None, **extra_fields):
        if not email and not cpf:
            raise ValueError("Informe e-mail ou CPF.")
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email or None, cpf=cpf or None, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("tipo_perfil", TipoPerfil.COORDENADOR)
        return self.create_user(email=email, password=password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=11, unique=True, null=True, blank=True, db_index=True)
    email = models.EmailField(unique=True, null=True, blank=True, db_index=True)
    tipo_perfil = models.CharField(max_length=20, choices=TipoPerfil.choices)
    must_change_password = models.BooleanField(default=False)

    coroinha = models.OneToOneField(
        "membership.Coroinha",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuario",
    )
    responsavel = models.OneToOneField(
        "membership.Responsavel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuario",
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(cpf__isnull=False) | models.Q(email__isnull=False)
                ),
                name="usuario_cpf_ou_email_obrigatorio",
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def is_familia(self) -> bool:
        return self.tipo_perfil in (TipoPerfil.PAI, TipoPerfil.COROINHA)

    @property
    def is_staff_pastoral(self) -> bool:
        return self.tipo_perfil in (
            TipoPerfil.COORDENADOR,
            TipoPerfil.SECRETARIO,
            TipoPerfil.PADRE,
        )
