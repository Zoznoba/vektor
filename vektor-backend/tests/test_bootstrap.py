import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vektor.core.config import settings
from vektor.core.security import verify_password
from vektor.modules.users.bootstrap import ensure_admin_exists
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

ADMIN_EMAIL = "boss@vektor.ru"
ADMIN_PASSWORD = "supersecret1"


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def admin_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_email", ADMIN_EMAIL)
    monkeypatch.setattr(settings, "admin_password", ADMIN_PASSWORD)


async def _get_users(db) -> list[User]:
    return list((await db.execute(select(User))).scalars().all())


async def test_creates_admin(db_session, admin_credentials) -> None:
    await ensure_admin_exists(db_session)

    users = await _get_users(db_session)
    assert len(users) == 1
    admin = users[0]
    assert admin.email == ADMIN_EMAIL
    assert admin.role == UserRole.ADMIN
    assert admin.is_active is True
    # Пароль хеширован и проверяется, в открытом виде не хранится
    assert admin.hashed_password != ADMIN_PASSWORD
    assert verify_password(ADMIN_PASSWORD, admin.hashed_password)


async def test_second_call_is_noop(db_session, admin_credentials) -> None:
    await ensure_admin_exists(db_session)
    await ensure_admin_exists(db_session)

    assert len(await _get_users(db_session)) == 1


async def test_skipped_without_credentials(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_email", None)
    monkeypatch.setattr(settings, "admin_password", None)

    await ensure_admin_exists(db_session)

    assert await _get_users(db_session) == []


async def test_existing_non_admin_is_not_promoted(db_session, admin_credentials) -> None:
    # На email админа уже зарегистрирован ученик (опечатка в ADMIN_EMAIL)
    student = User(
        email=ADMIN_EMAIL,
        hashed_password="irrelevant",
        full_name="Петя Иванов",
        role=UserRole.STUDENT,
    )
    db_session.add(student)
    await db_session.commit()

    await ensure_admin_exists(db_session)

    users = await _get_users(db_session)
    assert len(users) == 1
    assert users[0].role == UserRole.STUDENT
    assert users[0].hashed_password == "irrelevant"


async def test_admin_can_login_via_api(client, admin_credentials, db_engine) -> None:
    """Сквозная проверка: bootstrap → логин через реальный /auth/login."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        await ensure_admin_exists(session)

    response = await client.post(
        "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
