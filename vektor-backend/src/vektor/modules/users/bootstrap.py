# Идемпотентный bootstrap администратора. Вызывается из lifespan при старте.
#
# Инвариант: функцию можно звать сколько угодно раз — второй и последующие
# вызовы ничего не меняют. Это НЕ register_user из auth: тут нет HTTP-контекста,
# нет проверки «email уже занят = ошибка» — занятый email здесь норма (no-op).

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.config import settings
from vektor.core.security import hash_password
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

logger = logging.getLogger(__name__)

ADMIN_FULL_NAME = "Администратор"


async def ensure_admin_exists(db: AsyncSession) -> None:
    if not settings.admin_email or not settings.admin_password:
        logger.warning(
            "ADMIN_EMAIL/ADMIN_PASSWORD не заданы — bootstrap админа пропущен, "
            "в системе может не быть администратора"
        )
        return

    existing = (
        await db.execute(select(User).where(User.email == settings.admin_email))
    ).scalar_one_or_none()
    if existing is not None:
        if existing.role != UserRole.ADMIN:
            # Молча повышать роль нельзя: опечатка в ADMIN_EMAIL не должна
            # превращать случайного пользователя в администратора.
            logger.error(
                "Пользователь %s существует с ролью %s, а не admin — "
                "bootstrap его НЕ трогает; проверьте ADMIN_EMAIL",
                settings.admin_email,
                existing.role,
            )
        return

    db.add(
        User(
            email=settings.admin_email,
            hashed_password=hash_password(settings.admin_password),
            full_name=ADMIN_FULL_NAME,
            role=UserRole.ADMIN,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # Гонка при параллельном старте нескольких воркеров: оба не нашли
        # админа, оба сделали INSERT, второй упёрся в unique(email).
        # Значит, админ уже создан — это успех, а не ошибка.
        await db.rollback()
        return
    logger.info("Создан bootstrap-админ %s", settings.admin_email)
