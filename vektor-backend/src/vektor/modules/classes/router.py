from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import require_role
from vektor.modules.classes import service
from vektor.modules.classes.schemas import (
    AssignHomeroomIn,
    AssignStudentsIn,
    AssignTeachersIn,
    SchoolClassCreate,
    SchoolClassOut,
)
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/classes", tags=["classes"])


@router.post(
    "",
    response_model=SchoolClassOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать класс",
    description="Завести класс (например «8-1»). Только админ.",
)
async def create_school_class(
    data: SchoolClassCreate,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.create_class(db=db, grade=data.grade, section=data.section)


@router.get(
    "",
    response_model=list[SchoolClassOut],
    summary="Список классов",
    description="Все классы школы. Доступно админу и учителю.",
)
async def all_school_classes(
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN, UserRole.TEACHER)),
) -> list[SchoolClassOut]:
    return await service.all_classes(db)


@router.post(
    "/{class_id}/students",
    response_model=SchoolClassOut,
    summary="Привязать учеников к классу",
    description="Массово назначить учеников классу (bulk, по списку id). Только админ.",
)
async def assign_students_to_class(
    class_id: int,
    data: AssignStudentsIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.assign_students(db, class_id, data.student_ids)


@router.post(
    "/{class_id}/teachers",
    response_model=SchoolClassOut,
    summary="Привязать учителей к классу",
    description="Массово назначить учителей классу (bulk, по списку id, M2M). Только админ.",
)
async def assign_teachers_to_class(
    class_id: int,
    data: AssignTeachersIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.assign_teachers(db, class_id, data.teacher_ids)


@router.put(
    "/{class_id}/homeroom",
    response_model=SchoolClassOut,
    summary="Назначить классного руководителя",
    description="Кл. рук всегда один; назначение автоматически добавляет "
    "его в teachers класса. Только админ.",
)
async def assign_homeroom_teacher(
    class_id: int,
    data: AssignHomeroomIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.assign_homeroom(db, class_id, data.teacher_id)
