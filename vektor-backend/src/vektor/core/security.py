# Криптографические примитивы: хеширование паролей + JWT.
#
# Здесь только чистые функции без FastAPI и без БД — их легко тестировать
# и невозможно использовать неправильно из-за случайного импорта роутера.

import secrets
import string
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from vektor.core.config import settings

password_hash = PasswordHash.recommended()

HASH_ALGORITHM = "HS256"

# Без визуально путающихся символов (0/O, 1/l/I) — админ обычно диктует или
# копирует этот пароль пользователю, а не хранит его в менеджере паролей.
_TEMP_PASSWORD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI"
)


def generate_temporary_password(length: int = 12) -> str:
    """Случайный пароль для сброса админом (users.reset_password). Показывается
    вызывающему один раз в ответе — как settings.bulk_default_password для
    массовой загрузки, только без общего секрета на всех."""
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expire_time = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire_time}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=HASH_ALGORITHM)


def decode_access_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[HASH_ALGORITHM])
    return payload["sub"]
