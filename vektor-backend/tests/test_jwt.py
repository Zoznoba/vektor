# Юнит-тесты криптопримитивов (core/security.py).
# Чистые синхронные функции: ни БД, ни HTTP-клиента, ни async.

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from vektor.core.config import settings
from vektor.core.security import (
    HASH_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# --- Пароли ---


def test_hash_is_not_plaintext() -> None:
    assert hash_password("secret123") != "secret123"


def test_same_password_gives_different_hashes() -> None:
    assert hash_password("secret123") != hash_password("secret123")


def test_verify_accepts_correct_password() -> None:
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("secret123")
    assert verify_password("wrong-password", hashed) is False


# --- Токены ---


def test_token_roundtrip() -> None:
    token = create_access_token("42")
    assert decode_access_token(token) == "42"


def test_garbage_token_rejected() -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("abc.def.ghi")


def test_token_signed_with_other_key_rejected() -> None:
    # Токен корректной формы, но подписанный ЧУЖИМ ключом — главная атака,
    # от которой подпись JWT и защищает.
    forged = jwt.encode({"sub": "42"}, "attacker-secret", algorithm=HASH_ALGORITHM)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_expired_token_rejected() -> None:
    # Токен с exp в прошлом, подписанный нашим же ключом: подпись валидна,
    # но срок истёк — pyjwt отвергает его сам, без нашего кода.
    expired_payload = {
        "sub": "42",
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    token = jwt.encode(expired_payload, settings.jwt_secret_key, algorithm=HASH_ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)
