# Бизнес-логика cases. Проверка роли (только админ пишет) уже сделана в
# роутере через require_role(ADMIN) — здесь её дублировать не надо.
#
# Доменные исключения НЕ ловятся роутером: DomainError сам знает свой
# status_code и code, перевод в HTTP делает core/errors.py (Этап 7a).

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.errors import DomainError
from vektor.modules.cases.models import Case
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole


class CaseNotFound(DomainError):
    """Кейс с таким id не найден."""

    status_code = 404
    code = "case_not_found"
    message = "Кейс не найден"


class CaseAlreadyExists(DomainError):
    """Кейс с таким названием уже есть — иначе админ не различит их в списке."""

    status_code = 409
    code = "case_already_exists"
    message = "Кейс с таким названием уже существует"


class UserNotFound(DomainError):
    status_code = 404
    code = "user_not_found"
    message = "Пользователь не найден"


class WrongRole(DomainError):
    """Роль пользователя не подходит: в ученики кейса нельзя записать учителя
    и наоборот."""

    status_code = 409
    code = "wrong_role"
    message = "Роль пользователя не подходит для операции"


class AlreadyInAnotherCase(DomainError):
    """Пользователь уже состоит в ДРУГОМ кейсе.

    Молча перевешивать его сюда нельзя: и у ученика, и у учителя кейс ровно
    один, поэтому такая привязка тихо выкинула бы человека из прежнего кейса —
    почти наверняка не то, что имел в виду админ. Перевод делается явно:
    сначала DELETE из старого кейса, потом POST в новый.
    """

    status_code = 409
    code = "already_in_another_case"
    message = "Пользователь уже состоит в другом кейсе"


class NotInCase(DomainError):
    """Пользователь не состоит в этом кейсе — откреплять нечего."""

    status_code = 404
    code = "not_in_case"
    message = "Пользователь не состоит в этом кейсе"


class CaseNotEmpty(DomainError):
    """В кейсе ещё есть люди.

    Удаление пустого кейса безопасно, а вот с составом — нет: молчаливое
    открепление всех разом слишком похоже на случайное нажатие. Пусть админ
    сначала разберёт состав.

    (Снапшота Assessment.subject_case_id, который сделал бы удаление ещё и
    технически опасным, пока нет — см. NB в remove_members.)
    """

    status_code = 409
    code = "case_not_empty"
    message = "Сначала открепите всех участников кейса"


# Состав отдаём всегда целиком, поэтому догружаем обе проекции заранее: без
# этого сериализация CaseOut упадёт с MissingGreenlet (ленивая загрузка внутри
# async-сессии). Та же грабля, что у _CLASS_LOAD в classes/service.py:75.
_CASE_LOAD = (
    selectinload(Case.students),
    selectinload(Case.teachers),
)


async def _load_case(db: AsyncSession, case_id: int) -> Case:
    """Кейс со всем составом. Единственная точка загрузки — иначе каждый сервис
    заново решает, что догружать.

    ВАЖНО: `.execution_options(populate_existing=True)`, как в
    classes/service.py:87. Сессия живёт с expire_on_commit=False, и без него
    объект вернётся из identity map с коллекциями, загруженными ДО изменений —
    ответ показал бы состав кейса, каким он был до привязки.
    """
    result = await db.execute(
        select(Case)
        .where(Case.id == case_id)
        .options(*_CASE_LOAD)
        .execution_options(populate_existing=True)
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise CaseNotFound()
    return case


async def create_case(db: AsyncSession, name: str, description: str | None) -> Case:
    same_exist = await db.execute(select(Case).where(Case.name == name))
    if same_exist.scalar_one_or_none() is not None:
        raise CaseAlreadyExists()
    case = Case(name=name, description=description)
    db.add(case)
    await db.commit()
    return await _load_case(db, case.id)


async def all_cases(db: AsyncSession) -> list[Case]:
    cases = await db.execute(select(Case).options(*_CASE_LOAD).order_by(Case.name))
    return cases.scalars().all()


async def update_case(db: AsyncSession, case_id: int, changes: dict[str, Any]) -> Case:
    """Переименование / описание. `changes` — только реально пришедшие поля
    (роутер собирает их через exclude_unset), поэтому отсутствие ключа —
    «не трогать», а явный None в description — «стереть»."""
    case = await _load_case(db, case_id)

    if "name" in changes and changes["name"] is not None:
        clash = await db.execute(
            select(Case.id).where(Case.name == changes["name"], Case.id != case_id)
        )
        if clash.scalar_one_or_none() is not None:
            raise CaseAlreadyExists()
        case.name = changes["name"]

    if "description" in changes:
        case.description = changes["description"]

    await db.commit()
    return await _load_case(db, case_id)


async def assign_students(db: AsyncSession, case_id: int, user_ids: list[int]) -> Case:
    return await _assign_members(db, case_id, user_ids, UserRole.STUDENT)


async def assign_teachers(db: AsyncSession, case_id: int, user_ids: list[int]) -> Case:
    """Привязать учителей.

    Верхней границы «2–3 учителя» здесь НЕТ намеренно: это практика школы, а не
    инвариант данных (то же решение, что для 2–4 учителей класса в Этапе 7o).
    Предупреждает UI, запрещать нечего.
    """
    return await _assign_members(db, case_id, user_ids, UserRole.TEACHER)


async def _assign_members(
    db: AsyncSession, case_id: int, user_ids: list[int], expected_role: UserRole
) -> Case:
    """Общее ядро привязки: ученики и учителя различаются ТОЛЬКО ожидаемой
    ролью — колонка users.case_id одна на обоих.

    Порядок проверок важен: сначала валидируем всё, потом пишем. Если
    свалиться на середине цикла, часть людей уже окажется привязана —
    ровно та атомарность, о которой Этап 3.7.

    Проверки:
      1. все id существуют            → UserNotFound
      2. у всех роль == expected_role → WrongRole
      3. ни у кого нет ДРУГОГО кейса  → AlreadyInAnotherCase
         (уже в ЭТОМ кейсе — не ошибка, а no-op: привязка идемпотентна,
          как в 3.6 с родителями)
    """
    case = await _load_case(db, case_id)

    if not user_ids:
        return case

    found = await db.execute(select(User).where(User.id.in_(set(user_ids))))
    users = {user.id: user for user in found.scalars()}

    for user_id in user_ids:
        user = users.get(user_id)
        if user is None:
            raise UserNotFound()
        if user.role != expected_role:
            raise WrongRole()
        if user.case_id is not None and user.case_id != case_id:
            raise AlreadyInAnotherCase()

    for user_id in user_ids:
        users[user_id].case_id = case_id

    await db.commit()
    return await _load_case(db, case_id)


async def remove_member(db: AsyncSession, case_id: int, user_id: int) -> Case:
    """Открепить одного участника — частный случай remove_members.

    Отдельной логики здесь нет намеренно: одиночный DELETE и bulk-открепление
    обязаны вести себя одинаково, а два независимых пути с одинаковыми
    проверками рано или поздно разъезжаются.
    """
    return await remove_members(db, case_id, [user_id])


async def remove_members(db: AsyncSession, case_id: int, user_ids: list[int]) -> Case:
    """Открепить участников (учеников или учителей — вызов один).

    Человек остаётся в системе со всей историей — та же логика, что у
    remove_students_from_class: открепление зануляет users.case_id, а не
    удаляет пользователя.

    Валидация ВСЕЙ пачки идёт до записи — зеркально _assign_members: иначе
    падение на середине оставило бы состав разобранным наполовину, и админ не
    знал бы, кого уже открепило. Открепление НЕ идемпотентно (в отличие от
    привязки): человек, которого в этом кейсе нет, — это рассинхрон выделения
    на экране с реальным составом, и ответить на него молчанием значит скрыть
    от админа, что он открепил не тех.

    NB: снапшота кейса на анкете (Assessment.subject_case_id, по аналогии с
    subject_class_id) пока НЕТ — диагностика по кейсам не заводится. Когда
    заведётся, он понадобится по той же причине, что и у класса: переход
    ученика в другой кружок не должен переписывать прошлые результаты.
    """
    await _load_case(db, case_id)

    if not user_ids:
        return await _load_case(db, case_id)

    found = await db.execute(select(User).where(User.id.in_(set(user_ids))))
    users = {user.id: user for user in found.scalars()}

    for user_id in user_ids:
        user = users.get(user_id)
        if user is None:
            raise UserNotFound()
        if user.case_id != case_id:
            raise NotInCase()

    for user_id in user_ids:
        users[user_id].case_id = None

    await db.commit()
    return await _load_case(db, case_id)


async def delete_case(db: AsyncSession, case_id: int) -> None:
    """Удалить пустой кейс. С людьми внутри — 409: молчаливое открепление всех
    разом слишком похоже на случайное нажатие, пусть админ разберёт состав."""
    case = await _load_case(db, case_id)

    if case.students or case.teachers:
        raise CaseNotEmpty()

    await db.delete(case)
    await db.commit()
