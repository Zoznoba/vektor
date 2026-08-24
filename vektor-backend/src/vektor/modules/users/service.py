# Бизнес-логика users: связь родитель—ребёнок + массовая загрузка (Этап 3.7).
# Права проверяет роутер (require_role(ADMIN)), здесь — только доменные правила.

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.config import settings
from vektor.core.errors import DomainError
from vektor.core.security import generate_temporary_password, hash_password
from vektor.modules.classes.models import SchoolClass
from vektor.modules.users.models import User
from vektor.modules.users.schemas import BulkUserIn
from vektor.shared.enums import UserRole


class UserNotFound(DomainError):
    """Один или несколько пользователей с такими id не найдены."""

    status_code = 404
    code = "user_not_found"
    message = "Пользователь не найден"


class WrongRole(DomainError):
    """Роль пользователя не подходит для операции."""

    status_code = 409
    code = "wrong_role"
    message = "Роль пользователя не подходит для операции"


class DuplicateEmailsInBatch(DomainError):
    """В самом присланном списке есть повторяющиеся email (до всякой БД)."""

    status_code = 422
    code = "duplicate_emails_in_batch"
    message = "В списке есть повторяющиеся email"


class EmailsAlreadyTaken(DomainError):
    """Один или несколько email уже заняты пользователями в БД."""

    status_code = 409
    code = "emails_already_taken"
    message = "Некоторые email уже заняты"


class ClassNotFound(DomainError):
    """Указан class_id, но класса с таким id нет."""

    status_code = 404
    code = "class_not_found"
    message = "Класс не найден"


class CannotModifySelf(DomainError):
    """Админ пытается деактивировать сам себя."""

    status_code = 409
    code = "cannot_modify_self"
    message = "Нельзя изменить статус собственной учётной записи"


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


async def set_user_active(
    db: AsyncSession, user_id: int, is_active: bool, current_user: User
) -> User:
    """Включить/выключить учётку — единственная форма «удаления» пользователя
    в системе (soft-delete). is_active уже гейтит вход (auth/router.py) и
    все авторизованные запросы (get_current_user), так что деактивация
    перекрывает доступ мгновенно и без нового кода — здесь только сам
    переключатель и защита от самоблокировки.

    Не даём деактивировать самого себя: иначе админ, отключив свою же
    учётку, тут же теряет доступ к панели и включить её обратно уже некому.
    """
    if user_id == current_user.id:
        raise CannotModifySelf()

    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFound(f"Пользователь {user_id} не найден")

    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user


async def reset_password(db: AsyncSession, user_id: int) -> str:
    """Сгенерировать новый временный пароль и сохранить его хеш. Пароль
    возвращается вызывающему один раз простым текстом — как в
    bulk_create_users, другого способа узнать его потом не будет (почтовой
    рассылки в системе пока нет).

    Без защиты от self: в отличие от деактивации, сброс своего же пароля
    никого не запирает — новый пароль тут же показывается тому, кто его и
    запросил.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFound(f"Пользователь {user_id} не найден")

    new_password = generate_temporary_password()
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return new_password


async def bulk_create_users(
    db: AsyncSession, users: list[BulkUserIn], class_id: int | None
) -> list[User]:
    """Атомарно завести пачку пользователей. Всё или ничего: любая невалидная
    строка → исключение ДО commit, в БД не пишется ничего (стиль submit_answers).

    Всем на время тестов ставим один общий пароль settings.bulk_default_password
    (хешируем его). Если задан class_id — строки role=student привязываем к
    этому классу тем же вызовом; остальные роли к классу не трогаем.

    Возвращает список созданных User (роутер добьёт схему ответа).
    """
    emails = [u.email for u in users]
    duplicates = {email for email, count in Counter(emails).items() if count > 1}
    if duplicates:
        raise DuplicateEmailsInBatch(f"Повторяющиеся email в списке: {sorted(duplicates)}")

    existing_emails_query = await db.execute(select(User.email).where(User.email.in_(emails)))
    existing_emails = set(existing_emails_query.scalars().all())
    if existing_emails:
        raise EmailsAlreadyTaken(f"Email уже заняты: {sorted(existing_emails)}")

    if class_id is not None:
        school_class = await db.get(SchoolClass, class_id)
        if school_class is None:
            raise ClassNotFound(f"Класс {class_id} не найден")

    # 4. Все получают один общий тестовый пароль — хешируем его ОДИН раз, а не
    #    на каждого (bcrypt дорогой, а хеш общего пароля всё равно одинаков).
    hashed = hash_password(settings.bulk_default_password)
    new_users = [
        User(
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            hashed_password=hashed,
            # school_class_id только ученикам; прочим ролям класс не навязываем.
            school_class_id=class_id if u.role == UserRole.STUDENT else None,
        )
        for u in users
    ]
    db.add_all(new_users)

    # 5. Один commit — атомарно. refresh подтягивает id/created_at по
    #    server_default. UserOut без relationship'ов, так что MissingGreenlet
    #    здесь не грозит (в отличие от классов Этапа 3.5).
    await db.commit()
    for user in new_users:
        await db.refresh(user)
    return new_users
