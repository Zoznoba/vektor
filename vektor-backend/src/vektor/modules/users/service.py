# Бизнес-логика users: связь родитель—ребёнок. Права проверяет роутер
# (require_role(ADMIN)), здесь — только доменные правила.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.users.models import User
from vektor.shared.enums import UserRole


class UserNotFound(Exception):
    """Один или несколько пользователей с такими id не найдены."""


class WrongRole(Exception):
    """Роль пользователя не подходит для операции."""


async def get_parent_with_children(db: AsyncSession, parent_id: int) -> User:
    result = await db.execute(
        select(User).where(User.id == parent_id).options(selectinload(User.children))
    )
    parent = result.scalar_one_or_none()
    if parent is None:
        raise UserNotFound(f"Пользователь {parent_id} не найден")
    if parent.role != UserRole.PARENT:
        raise WrongRole(f"Пользователь {parent_id} — {parent.role}, а не родитель")
    return parent


async def assign_children(db: AsyncSession, parent_id: int, child_ids: list[int]) -> User:
    """Привязать детей к родителю. Bulk и идемпотентно: уже привязанные
    дети в списке — не ошибка, просто пропускаются."""

    parent = await get_parent_with_children(db, parent_id)

    children_query = await db.execute(select(User).where(User.id.in_(child_ids)))
    children = children_query.scalars().all()

    found_ids = {u.id for u in children}
    missing_ids = set(child_ids) - found_ids
    if missing_ids:
        raise UserNotFound(f"Не найдены пользователи: {missing_ids}")

    not_students = [u.id for u in children if u.role != UserRole.STUDENT]
    if not_students:
        raise WrongRole(f"Привязать можно только учеников, не подходят: {not_students}")

    already_linked = {c.id for c in parent.children}
    parent.children.extend(c for c in children if c.id not in already_linked)

    await db.commit()
    await db.refresh(parent, attribute_names=["children"])
    return parent
