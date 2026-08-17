# Этап 7 — ограничение частоты запросов.
#
# Единственный файл, где лимит включён: в остальных он выключен фикстурой
# _disable_rate_limit (см. conftest.py), иначе суита блокирует сама себя.
#
# Счётчики живут в Redis и переживают не только тест, но и весь прогон (TTL
# окна регистрации — 5 минут), поэтому сносятся до и после каждого теста.
# Пороги в settings тоже восстанавливаются: объект глобальный, иначе поведение
# зависело бы от порядка запуска тестов.

import pytest
from httpx import AsyncClient

from vektor.core.config import settings
from vektor.core.rate_limit import client_key, close_redis, get_redis

_TUNABLES = (
    "rate_limit_enabled",
    "login_rate_limit",
    "login_rate_window_seconds",
    "register_rate_limit",
    "register_rate_window_seconds",
)


@pytest.fixture(autouse=True)
def _enable_rate_limit():
    """Включить лимит и ВЕРНУТЬ все пороги после теста.

    settings — глобальный объект: без восстановления порог, выставленный одним
    тестом, дотёк бы до следующих и поведение зависело бы от порядка запуска.
    """
    saved = {name: getattr(settings, name) for name in _TUNABLES}
    settings.rate_limit_enabled = True
    yield
    for name, value in saved.items():
        setattr(settings, name, value)
    settings.rate_limit_enabled = False


@pytest.fixture(autouse=True)
async def _clean_keys():
    """Убрать за собой ключи и закрыть клиент Redis.

    Закрывать обязательно: клиент кешируется в модуле и привязывается к тому
    event loop, в котором был создан, а pytest-asyncio даёт каждому тесту свой
    loop. Без закрытия следующий тест получил бы соединение от уже закрытого
    loop'а («attached to a different loop»). В приложении этой проблемы нет —
    там loop один на всё время жизни процесса.
    """
    await _flush_counters()
    yield
    try:
        await _flush_counters()
    except Exception:
        # Тест мог подменить клиент на сломанный (проверка fail-open) —
        # уборка не должна из-за этого падать.
        pass
    finally:
        await close_redis()


async def _flush_counters() -> None:
    """Снести ВСЕ счётчики, а не только с ключами тестов.

    Часть запросов идёт без X-Forwarded-For (фикстура register_user в
    conftest), и такие попадают в общий ключ. Он переживает не только тест, но
    и весь прогон: TTL у окна регистрации 5 минут, поэтому неудачный прогон
    ронял бы следующие ещё несколько минут. Счётчики эфемерны, сносить их
    целиком безопасно.
    """
    redis = get_redis()
    keys = [key async for key in redis.scan_iter("ratelimit:*")]
    if keys:
        await redis.delete(*keys)


def _from(ip: str) -> dict[str, str]:
    # X-Forwarded-For — то, по чему лимитер отличает клиентов за прокси.
    return {"X-Forwarded-For": ip}


async def _login_attempt(client: AsyncClient, ip: str):
    return await client.post(
        "/auth/login",
        json={"email": "nobody@vektor.ru", "password": "wrong"},
        headers=_from(ip),
    )


# --- client_key ---


def test_client_key_prefers_forwarded_header() -> None:
    class _Req:
        headers = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        client = None

    # Берём ПЕРВЫЙ элемент цепочки — исходный клиент, а не промежуточный прокси.
    assert client_key(_Req()) == "203.0.113.7"


def test_client_key_without_forwarded_header() -> None:
    class _Client:
        host = "192.0.2.5"

    class _Req:
        headers: dict[str, str] = {}
        client = _Client()

    assert client_key(_Req()) == "192.0.2.5"


# --- поведение лимита ---


async def test_login_blocked_after_limit(client: AsyncClient) -> None:
    settings.login_rate_limit = 3
    ip = "test-block"

    for attempt in range(3):
        response = await _login_attempt(client, ip)
        assert response.status_code == 401, f"попытка {attempt} не должна блокироваться"

    blocked = await _login_attempt(client, ip)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"


async def test_blocked_response_has_retry_after(client: AsyncClient) -> None:
    settings.login_rate_limit = 1
    ip = "test-retry"

    await _login_attempt(client, ip)
    blocked = await _login_attempt(client, ip)

    assert blocked.status_code == 429
    # Клиенту нужно знать, когда повторить, иначе он будет долбиться вслепую.
    assert int(blocked.headers["Retry-After"]) > 0


async def test_limit_is_per_client(client: AsyncClient) -> None:
    # Счётчик у каждого свой: заблокированный сосед не должен закрывать вход
    # всей школе, выходящей в интернет через один адрес... но за общим NAT
    # адрес и правда общий — поэтому пороги подобраны с запасом.
    settings.login_rate_limit = 1

    await _login_attempt(client, "test-a")
    blocked = await _login_attempt(client, "test-a")
    other = await _login_attempt(client, "test-b")

    assert blocked.status_code == 429
    assert other.status_code == 401


async def test_successful_login_also_counts(client: AsyncClient, register_user) -> None:
    # Лимит на ПОПЫТКИ, а не на неудачи: иначе перебор чередованием удачного
    # и неудачного входа обходил бы счётчик.
    settings.login_rate_limit = 2
    ip = "test-success"

    first = await client.post("/auth/login", json=register_user, headers=_from(ip))
    second = await client.post("/auth/login", json=register_user, headers=_from(ip))
    third = await client.post("/auth/login", json=register_user, headers=_from(ip))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


async def test_register_has_its_own_counter(client: AsyncClient) -> None:
    # Разные scope — независимые счётчики: исчерпанные регистрации не должны
    # закрывать вход.
    settings.register_rate_limit = 1
    settings.login_rate_limit = 10
    ip = "test-scopes"

    await client.post(
        "/auth/register",
        json={
            "email": "r1@vektor.ru",
            "password": "password123",
            "full_name": "Р",
            "role": "student",
        },
        headers=_from(ip),
    )
    blocked = await client.post(
        "/auth/register",
        json={
            "email": "r2@vektor.ru",
            "password": "password123",
            "full_name": "Р",
            "role": "student",
        },
        headers=_from(ip),
    )
    login = await _login_attempt(client, ip)

    assert blocked.status_code == 429
    assert login.status_code == 401  # вход не задет


async def test_fails_open_when_redis_unavailable(client: AsyncClient, monkeypatch) -> None:
    # Осознанный компромисс: падение Redis не должно превращаться в полную
    # невозможность войти. Ограничение частоты — смягчающая мера, а не
    # проверка прав.
    settings.login_rate_limit = 1

    class _BrokenRedis:
        async def incr(self, key):
            raise ConnectionError("redis is down")

    monkeypatch.setattr("vektor.core.rate_limit.get_redis", lambda: _BrokenRedis())

    for _ in range(3):
        response = await _login_attempt(client, "test-open")
        assert response.status_code == 401  # пропускаем, а не 429 и не 500
