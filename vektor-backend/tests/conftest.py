# Общие фикстуры pytest.
#
# Главная идея: тесты НИКОГДА не ходят в рабочую базу vektor.
# Используется отдельная база vektor_test (создаётся автоматически),
# и перед каждым тестом схема строится с нуля, а после — сносится.
# Медленнее, чем транзакция с откатом, но железно изолированно и просто;
# оптимизируем, когда тестов станут сотни.

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vektor.core.config import settings
from vektor.core.database import Base, get_db
from vektor.main import app

TEST_DB_NAME = "vektor_test"
TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"

REGISTER_DATA = {
    "email": "petya@vektor.ru",
    "password": "password123",
    "full_name": "Петя Иванов",
    "role": "student",
}


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> None:
    """Однократно на весь прогон: создать базу vektor_test, если её нет.

    CREATE DATABASE нельзя выполнять в транзакции, поэтому autocommit.
    Фикстура синхронная (см. asyncio.run) — чтобы не связываться с
    session-scoped event loop'ом pytest-asyncio.
    """

    async def create() -> None:
        admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
        admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        await admin.dispose()

    asyncio.run(create())


@pytest.fixture
async def db_engine():
    """Свежий движок к тестовой базе + чистая схема на каждый тест."""
    engine = create_async_engine(TEST_DATABASE_URL)  # echo не нужен: шумно в тестах
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(db_engine):
    """HTTP-клиент к приложению, у которого get_db подменён на тестовую БД.

    app.dependency_overrides — тот самый механизм, ради которого get_db
    оформлен зависимостью: роутеры не знают, что база ненастоящая.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def register_user(client: AsyncClient) -> dict[str, str]:
    await client.post("/auth/register", json=REGISTER_DATA)
    return {"email": REGISTER_DATA["email"], "password": REGISTER_DATA["password"]}
