from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import require_role
from vektor.modules.classes import service
from vektor.modules.classes.schemas import (
    AssignStudentsIn,
    AssignTeachersIn,
    SchoolClassCreate,
    SchoolClassOut,
    UpdateTeacherInClassIn,
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
    description="Массово назначить учителей классу (bulk, по списку id, M2M). "
    "Опционально сразу задать предмет и/или классное руководство — общие на "
    "всю пачку. Только админ.",
)
async def assign_teachers_to_class(
    class_id: int,
    data: AssignTeachersIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.assign_teachers(
        db, class_id, data.teacher_ids, data.subject, data.is_homeroom
    )


@router.patch(
    "/{class_id}/teachers/{teacher_id}",
    response_model=SchoolClassOut,
    summary="Изменить предмет или классное руководство",
    description="Правка связи «учитель ↔ класс». Передавайте только те поля, "
    "которые меняете: отсутствующий ключ остаётся как был, явный "
    '`"subject": null` стирает предмет. Классных руководителей у класса '
    "может быть несколько. Только админ.",
)
async def update_teacher_in_class(
    class_id: int,
    teacher_id: int,
    data: UpdateTeacherInClassIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.update_teacher_in_class(
        db, class_id, teacher_id, data.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{class_id}/teachers/{teacher_id}",
    response_model=SchoolClassOut,
    summary="Открепить учителя от класса",
    description="Убрать учителя из класса. Классное руководство снимается "
    "вместе со связью. Сам пользователь остаётся в системе. Только админ.",
)
async def remove_teacher_from_class(
    class_id: int,
    teacher_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.remove_teacher_from_class(db, class_id, teacher_id)


@router.delete(
    "/{class_id}/students/{student_id}",
    response_model=SchoolClassOut,
    summary="Открепить ученика от класса",
    description="Ученик остаётся в системе и сохраняет историю: анкеты "
    "хранят снапшот класса, прошлые результаты не меняются. Для перевода в "
    "другой класс используйте привязку к новому классу — она перезаписывает "
    "старый. Только админ.",
)
async def remove_student_from_class(
    class_id: int,
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.remove_student_from_class(db, class_id, student_id)
