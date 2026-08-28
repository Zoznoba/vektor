from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import require_role
from vektor.modules.cases import service
from vektor.modules.cases.schemas import AssignMembersIn, CaseCreate, CaseOut, CaseUpdate
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


# TODO: PATCH "/{case_id}" — переименование/описание.
#  Тело CaseUpdate, в сервис отдавать data.model_dump(exclude_unset=True) —
#  как update_teacher_in_class (classes/router.py:98). Только админ.

# TODO: POST "/{case_id}/students" и POST "/{case_id}/teachers" — bulk-привязка,
#  тело AssignMembersIn, ответ CaseOut. Только админ.

# TODO: DELETE "/{case_id}/members/{user_id}" — открепить участника.
#  Один эндпоинт на учеников и учителей: сервис различает их по роли, а
#  разводить два одинаковых пути ради этого незачем. Ответ CaseOut.

# TODO: DELETE "/{case_id}" — удалить пустой кейс.
#  Ответ — status_code=204 и None (тела нет), см. как это делается в
#  competencies/router.py у отмены черновика.
