"""Сброс паролей демо-учёток на локальный BULK_DEFAULT_PASSWORD.

Зачем это нужно. В `demo_data.sql` лежат ГОТОВЫЕ argon2-хеши, посчитанные от
значения `BULK_DEFAULT_PASSWORD` той машины, где дамп снимали. `.env` в git не
коммитится, поэтому на любой другой машине это значение другое — и войти под
демо-учёткой невозможно, а хеш не развернуть обратно. Без этого шага демо
разворачивается, но остаётся некликабельным.

Скрипт идемпотентен: гоняйте сколько угодно, эффект один и тот же.

    uv run python seed/reset_demo_passwords.py

Служебные респонденты (`is_placeholder = true`) пропускаются: они не люди и не
логинятся (`is_active = false`), пароль им ни к чему.
"""

import asyncio

import sqlalchemy as sa

from vektor.core.config import settings
from vektor.core.database import async_session_factory
from vektor.core.security import hash_password


async def reset() -> None:
    # Хеш считаем ОДИН раз на всех — argon2 намеренно медленный, а учёток
    # под сотню. Тот же приём, что в bulk_create_users (Этап 3.7).
    hashed = hash_password(settings.bulk_default_password)

    # Намеренно голый SQL, а не ORM: скрипт живёт вне приложения, и импорта
    # одной модели User не хватило бы — маппер не смог бы разрешить
    # relationship на SchoolClass, пока не импортированы все модели разом.
    # Задача тут ровно одна — UPDATE одной колонки, ORM для неё лишний.
    async with async_session_factory() as session:
        result = await session.execute(
            sa.text(
                "UPDATE users SET hashed_password = :h WHERE is_placeholder = false RETURNING id"
            ),
            {"h": hashed},
        )
        updated = len(result.all())
        await session.commit()

    print(f"Обновлено учёток: {updated}")
    print(f"Пароль для входа: {settings.bulk_default_password}")


if __name__ == "__main__":
    asyncio.run(reset())
