# Подключение к БД: engine, фабрика сессий, зависимость get_db.
#
# Ключевая идея (важно понять до написания кода):
#   - engine — ОДИН на всё приложение. Это пул соединений с Postgres.
#     Создаётся при старте, закрывается при остановке.
#   - сессия — ОДНА на каждый HTTP-запрос. Короткоживущая рабочая
#     единица: открыл, поработал, закрыл. Берёт соединение из пула engine.

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from vektor.core.config import settings


class Base(DeclarativeBase):
    """Общий предок всех ORM-моделей проекта.

    naming_convention даёт всем индексам/ключам/констрейнтам предсказуемые
    имена (ix_..., fk_..., pk_...). Без этого Postgres придумывает имена сам,
    и автогенерация миграций Alembic со временем начинает «дребезжать» —
    видеть несуществующие отличия схем.
    """

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


engine = create_async_engine(url=settings.database_url, echo=(settings.environment == "local"))

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
