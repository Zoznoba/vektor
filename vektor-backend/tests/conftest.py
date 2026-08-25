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
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from vektor.core.config import settings
from vektor.core.database import Base, get_db
from vektor.main import app
from vektor.modules.competencies.models import OutcomeArea, QuestionnaireVersion

TEST_DB_NAME = "vektor_test"
TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"

REGISTER_DATA = {
    "email": "petya@vektor.ru",
    "password": "password123",
    "full_name": "Петя Иванов",
    "role": "student",
}


@pytest.fixture(autouse=True)
def _disable_rate_limit() -> None:
    """Ограничение частоты выключено во всех тестах, кроме тех, что проверяют
    его самого (test_rate_limit.py включает флаг обратно).

    Иначе суита сама себя блокирует: она делает десятки логинов и регистраций
    подряд, а Redis — общий и между тестами не чистится.
    """
    settings.rate_limit_enabled = False


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
        # Действующая редакция анкеты — то, что в проде ставит миграция
        # c3f81ad0e7b5. Без неё create_campaign не сможет выбрать версию, а
        # вопросы не к чему привязать (Question.version_id NOT NULL).
        await conn.execute(
            insert(QuestionnaireVersion.__table__).values(
                code="test-current", title="Тестовая редакция", is_current=True
            )
        )
        # «ОР / навык» верхнего уровня: Competency.outcome_area_id — NOT NULL,
        # поэтому хотя бы одна область нужна любому тесту, создающему критерий.
        await conn.execute(
            insert(OutcomeArea.__table__).values(code="test-area", name="Тестовая область", order=0)
        )
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


@pytest.fixture
async def admin_headers(client: AsyncClient) -> dict[str, str]:
    """Регистрирует админа и возвращает готовый заголовок Authorization.

    Email намеренно отличается от REGISTER_DATA — иначе тест, где в одном
    прогоне участвуют и обычный пользователь, и админ, столкнётся
    с EmailAlreadyRegistered (в тестовой БД email по-прежнему уникален).
    """
    admin_data = {
        "email": "admin@vektor.ru",
        "password": "password123",
        "full_name": "Админ Админов",
        "role": "admin",
    }
    await client.post("/auth/register", json=admin_data)
    login = await client.post(
        "/auth/login",
        json={"email": admin_data["email"], "password": admin_data["password"]},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def existing_class(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    """Готовый класс (создан через реальный API) + заголовки админа под ключом _headers."""
    response = await client.post(
        "/classes", json={"grade": 7, "section": "a"}, headers=admin_headers
    )
    return {**response.json(), "_headers": admin_headers}
