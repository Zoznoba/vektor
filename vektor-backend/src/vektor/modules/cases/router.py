from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import require_role
from vektor.modules.cases import service
from vektor.modules.cases.schemas import (
    AssignMembersIn,
    CaseCreate,
    CaseOut,
    CaseUpdate,
    RemoveMembersIn,
)
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/cases", tags=["cases"])


# Роутеры тонкие: только распаковать тело и позвать сервис. Доменные
# исключения наверх не ловим — их переводит register_error_handlers.


@router.post(
    "",
    response_model=CaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать кейс",
    description="Завести профильную группу (кружок). Только админ.",
)
async def create_case(
    data: CaseCreate,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    return await service.create_case(db, data.name, data.description)


@router.get(
    "",
    response_model=list[CaseOut],
    summary="Список кейсов",
    description="Все кейсы школы с составом. Доступно админу и учителю "
    "(учителю — чтобы найти свой кейс на экране «Мои кейсы»).",
)
async def all_cases(
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN, UserRole.TEACHER)),
) -> list[CaseOut]:
    return await service.all_cases(db)


@router.patch(
    "/{case_id}",
    response_model=CaseOut,
    summary="Переименовать кейс",
    description="Частичная правка названия и описания: отсутствие ключа в теле "
    "означает «не трогать», а явный `null` в description — «стереть». Только админ.",
)
async def update_case(
    case_id: int,
    data: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    # exclude_unset: именно он превращает «поля не было в теле» в «не трогать».
    return await service.update_case(db, case_id, data.model_dump(exclude_unset=True))


@router.post(
    "/{case_id}/students",
    response_model=CaseOut,
    summary="Привязать учеников к кейсу",
    description="Bulk-привязка списком id за один вызов. Повторная привязка "
    "того, кто уже в этом кейсе, — не ошибка (no-op); человек из ДРУГОГО кейса "
    "даёт 409: перевод делается явно, через открепление. Только админ.",
)
async def assign_students(
    case_id: int,
    data: AssignMembersIn,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    return await service.assign_students(db, case_id, data.user_ids)


@router.post(
    "/{case_id}/teachers",
    response_model=CaseOut,
    summary="Привязать учителей к кейсу",
    description="То же, что привязка учеников, но роль проверяется на teacher. "
    "Верхней границы «2–3 учителя» нет: это практика школы, а не инвариант "
    "данных — предупреждает UI. Только админ.",
)
async def assign_teachers(
    case_id: int,
    data: AssignMembersIn,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    return await service.assign_teachers(db, case_id, data.user_ids)


@router.post(
    "/{case_id}/members/detach",
    response_model=CaseOut,
    summary="Открепить участников от кейса (bulk)",
    description="Открепить сразу нескольких учеников и/или учителей одним "
    "вызовом — зеркально bulk-привязке. Атомарно: если хоть кого-то из списка "
    "в кейсе нет, не открепляется никто (409). POST, а не DELETE, потому что "
    "тело у DELETE режут прокси. Только админ.",
)
async def remove_members(
    case_id: int,
    data: RemoveMembersIn,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    return await service.remove_members(db, case_id, data.user_ids)


@router.delete(
    "/{case_id}/members/{user_id}",
    response_model=CaseOut,
    summary="Открепить участника от кейса",
    description="Один эндпоинт на учеников и учителей: сервис различает их по "
    "роли, разводить два одинаковых пути ради этого незачем. Человек остаётся "
    "в системе со всей историей. Только админ.",
)
async def remove_member(
    case_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> CaseOut:
    return await service.remove_member(db, case_id, user_id)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить кейс",
    description="Удалить пустой кейс. Если в составе ещё есть люди — 409: "
    "сначала открепите участников. Только админ.",
)
async def delete_case(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN)),
) -> None:
    await service.delete_case(db, case_id)
