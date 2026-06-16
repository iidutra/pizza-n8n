"""Configuração para testes — SQLite em memória, cache local, senhas rápidas."""

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MEDIA_ROOT = BASE_DIR / "test_media"  # noqa: F405

USE_SQLITE = True
USE_REDIS = False

AUTH_RATE_LIMIT_ATTEMPTS = 100
AUTH_RATE_LIMIT_WINDOW = 60
