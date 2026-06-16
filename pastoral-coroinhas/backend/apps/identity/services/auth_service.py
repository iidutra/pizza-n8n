import hashlib

import structlog
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from apps.identity.models import TipoPerfil, Usuario
from apps.identity.utils.cpf import normalizar_cpf, validar_cpf

logger = structlog.get_logger(__name__)

RECUPERACAO_ERRO = "CPF ou data de nascimento incorretos."
LOGIN_ERRO = "Credenciais inválidas."


class AuthService:
    @staticmethod
    def _rate_limit_key(prefix: str, cpf: str, ip: str | None) -> str:
        cpf_hash = hashlib.sha256(cpf.encode()).hexdigest()[:16]
        ip_part = ip or "unknown"
        return f"auth:{prefix}:{cpf_hash}:{ip_part}"

    @classmethod
    def _check_rate_limit(cls, prefix: str, cpf: str, ip: str | None) -> None:
        key = cls._rate_limit_key(prefix, cpf, ip)
        attempts = cache.get(key, 0)
        if attempts >= settings.AUTH_RATE_LIMIT_ATTEMPTS:
            logger.warning("auth_rate_limit_exceeded", prefix=prefix)
            raise ValueError("Muitas tentativas. Tente novamente mais tarde.")
        cache.set(key, attempts + 1, settings.AUTH_RATE_LIMIT_WINDOW)

    @classmethod
    def login(cls, identificador: str, senha: str, ip: str | None = None) -> Usuario:
        identificador = identificador.strip()
        if "@" in identificador:
            return cls.login_staff(identificador, senha, ip)
        return cls.login_familia(identificador, senha, ip)

    @classmethod
    def login_familia(cls, cpf: str, senha: str, ip: str | None = None) -> Usuario:
        cpf = normalizar_cpf(cpf)
        if not validar_cpf(cpf):
            raise ValueError(LOGIN_ERRO)

        cls._check_rate_limit("login", cpf, ip)

        try:
            usuario = Usuario.objects.get(cpf=cpf, is_active=True)
        except Usuario.DoesNotExist:
            raise ValueError(LOGIN_ERRO) from None

        if usuario.tipo_perfil not in (TipoPerfil.PAI, TipoPerfil.COROINHA):
            raise ValueError(LOGIN_ERRO)

        if not usuario.check_password(senha):
            raise ValueError(LOGIN_ERRO)

        logger.info("login_sucesso", usuario_id=usuario.id, tipo_perfil=usuario.tipo_perfil)
        return usuario

    @classmethod
    def login_staff(cls, email: str, senha: str, ip: str | None = None) -> Usuario:
        email = email.strip().lower()
        cls._check_rate_limit("login", email, ip)

        try:
            usuario = Usuario.objects.get(
                Q(email__iexact=email),
                is_active=True,
                tipo_perfil__in=(TipoPerfil.COORDENADOR, TipoPerfil.SECRETARIO, TipoPerfil.PADRE),
            )
        except Usuario.DoesNotExist:
            raise ValueError(LOGIN_ERRO) from None

        if not usuario.check_password(senha):
            raise ValueError(LOGIN_ERRO)

        logger.info("login_sucesso", usuario_id=usuario.id, tipo_perfil=usuario.tipo_perfil)
        return usuario

    @staticmethod
    def _validar_data_nascimento_recuperacao(usuario: Usuario, data_nascimento) -> bool:
        if usuario.tipo_perfil == TipoPerfil.COROINHA:
            return usuario.coroinha and usuario.coroinha.data_nascimento == data_nascimento
        if usuario.tipo_perfil == TipoPerfil.PAI:
            return (
                usuario.responsavel
                and usuario.responsavel.coroinhas.filter(data_nascimento=data_nascimento).exists()
            )
        return False

    @classmethod
    def recuperar_senha(
        cls,
        cpf: str,
        data_nascimento,
        nova_senha: str,
        ip: str | None = None,
    ) -> None:
        cpf = normalizar_cpf(cpf)
        if not validar_cpf(cpf):
            logger.info("recuperar_senha_falha", motivo="cpf_invalido")
            raise ValueError(RECUPERACAO_ERRO)

        cls._check_rate_limit("recuperar", cpf, ip)

        try:
            usuario = Usuario.objects.get(
                cpf=cpf,
                is_active=True,
                tipo_perfil__in=(TipoPerfil.PAI, TipoPerfil.COROINHA),
            )
        except Usuario.DoesNotExist:
            logger.info("recuperar_senha_falha", motivo="usuario_nao_encontrado")
            raise ValueError(RECUPERACAO_ERRO) from None

        if not cls._validar_data_nascimento_recuperacao(usuario, data_nascimento):
            logger.info("recuperar_senha_falha", motivo="data_nascimento", usuario_id=usuario.id)
            raise ValueError(RECUPERACAO_ERRO)

        usuario.set_password(nova_senha)
        usuario.must_change_password = False
        usuario.save(update_fields=["password", "must_change_password"])
        logger.info("recuperar_senha_sucesso", usuario_id=usuario.id)

    @classmethod
    def trocar_senha(cls, usuario: Usuario, senha_atual: str, nova_senha: str) -> None:
        if not usuario.check_password(senha_atual):
            raise ValueError("Senha atual incorreta.")
        usuario.set_password(nova_senha)
        usuario.must_change_password = False
        usuario.save(update_fields=["password", "must_change_password"])
        logger.info("trocar_senha_sucesso", usuario_id=usuario.id)
