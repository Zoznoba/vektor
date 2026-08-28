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

    Удаление пустого кейса безопасно, а вот с составом — нет: снапшот
    Assessment.subject_case_id ссылается на строку, и молчаливое открепление
    всех разом слишком похоже на случайное нажатие. Пусть админ сначала
    разберёт состав.
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
    # TODO: select(Case).where(...).options(*_CASE_LOAD).execution_options(...)
    # TODO: нет — raise CaseNotFound
    raise NotImplementedError


async def create_case(db: AsyncSession, name: str, description: str | None) -> Case:
    # TODO: проверить, что кейса с таким name ещё нет → иначе CaseAlreadyExists.
    #  Как в create_class: отдельным select'ом ЗАРАНЕЕ, а не ловить падение
    #  unique-констрейнта на вставке (тот же приём, что в bulk-загрузке 3.7).
    # TODO: создать, db.add, await db.commit(), вернуть await _load_case(...)
    raise NotImplementedError


async def all_cases(db: AsyncSession) -> list[Case]:
    # TODO: select(Case).options(*_CASE_LOAD), упорядочить по name —
    #  список без ORDER BY возвращается в произвольном порядке, и карточки на
    #  экране будут прыгать между запросами.
    raise NotImplementedError


async def update_case(db: AsyncSession, case_id: int, changes: dict[str, Any]) -> Case:
    """Переименование / описание. `changes` — только реально пришедшие поля
    (роутер собирает их через exclude_unset), поэтому отсутствие ключа —
    «не трогать», а явный None в description — «стереть»."""
    # TODO: загрузить кейс, применить изменения по тому же принципу, что
    #  update_teacher_in_class (classes/service.py:164): проверять `in changes`,
    #  а не истинность значения.
    # TODO: при смене name — снова проверить уникальность (CaseAlreadyExists),
    #  но НЕ считать конфликтом сам себя.
    raise NotImplementedError


async def assign_students(db: AsyncSession, case_id: int, user_ids: list[int]) -> Case:
    # TODO: делегировать в _assign_members с expected_role=UserRole.STUDENT
    raise NotImplementedError


async def assign_teachers(db: AsyncSession, case_id: int, user_ids: list[int]) -> Case:
    # TODO: делегировать в _assign_members с expected_role=UserRole.TEACHER
    #
    #  Верхней границы «2–3 учителя» здесь НЕТ намеренно: это практика школы,
    #  а не инвариант данных (то же решение, что для 2–4 учителей класса в
    #  Этапе 7o). Предупреждает UI, запрещать нечего.
    raise NotImplementedError


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
    # TODO: загрузить кейс (_load_case) и пользователей одним select'ом
    # TODO: три проверки выше
    # TODO: проставить user.case_id = case_id, commit, вернуть _load_case
    raise NotImplementedError


async def remove_member(db: AsyncSession, case_id: int, user_id: int) -> Case:
    """Открепить участника (ученика или учителя — вызов один).

    Человек остаётся в системе со всей историей: анкеты хранят снапшот
    Assessment.subject_case_id, поэтому прошлые результаты кейса открепление
    не меняет — та же логика, что у remove_student_from_class.
    """
    # TODO: проверить, что пользователь существует (UserNotFound) и его
    #  case_id == case_id (иначе NotInCase — открепление относится не к нему)
    # TODO: user.case_id = None, commit, вернуть _load_case
    raise NotImplementedError


async def delete_case(db: AsyncSession, case_id: int) -> None:
    # TODO: загрузить кейс; если students или teachers непусты → CaseNotEmpty
    # TODO: удалить строку, commit
    raise NotImplementedError
