# Подключение к БД: engine, фабрика сессий, зависимость get_db.
#
# Ключевая идея (важно понять до написания кода):
#   - engine — ОДИН на всё приложение. Это пул соединений с Postgres.
#     Создаётся при старте, закрывается при остановке.
#   - сессия — ОДНА на каждый HTTP-запрос. Короткоживущая рабочая
#     единица: открыл, поработал, закрыл. Берёт соединение из пула engine.

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vektor.core.config import settings

engine = create_async_engine(
    url=settings.database_url,
    echo=(settings.environment=="local")
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session