from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import require_role
from vektor.modules.classes import service
from vektor.modules.classes.schemas import (
    ApplyPromotionIn,
    AssignStudentsIn,
    AssignTeachersIn,
    PreviewPromotionIn,
    PromotionPlanOut,
    PromotionRunOut,
    RemoveStudentsIn,
    RemoveTeachersIn,
    SchoolClassCreate,
    SchoolClassOut,
    UpdateTeacherInClassIn,
)
from vektor.modules.users.models import User
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
    "/promotion/preview",
    response_model=PromotionPlanOut,
    summary="Предпросмотр перевода на новый учебный год",
    description="Сухой прогон: показывает, кто в какой класс перейдёт, какие "
    "классы будут созданы и кто выпускается. В БД ничего не меняет. "
    "`section_overrides` — переопределение целевой секции по id исходного "
    "класса. Только админ.",
)
async def preview_promotion(
    data: PreviewPromotionIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> PromotionPlanOut:
    return await service.preview_promotion(db, data.section_overrides)


@router.post(
    "/promotion/apply",
    response_model=PromotionRunOut,
    summary="Выполнить перевод на новый учебный год",
    description="Одной транзакцией: создаёт недостающие целевые классы, "
    "переносит учеников, деактивирует и открепляет выпускников 11-х классов. "
    "`confirm_academic_year` должен точно совпасть с текущим учебным годом "
    "(защита от случайного запуска). Повторный запуск за тот же год — 409. "
    "Идемпотентно по ученикам: уже переведённые пропускаются. Только админ.",
)
async def apply_promotion(
    data: ApplyPromotionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
) -> PromotionRunOut:
    return await service.apply_promotion(
        db,
        data.section_overrides,
        data.carry_teachers_for,
        data.confirm_academic_year,
        current_user,
    )


@router.get(
    "/promotion/current",
    response_model=PromotionRunOut | None,
    summary="Активный перевод за текущий учебный год",
    description="Возвращает запуск перевода за текущий учебный год, если он был, "
    "иначе null. `can_undo=false`, если после перевода уже создана кампания. "
    "Только админ.",
)
async def current_promotion(
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> PromotionRunOut | None:
    return await service.current_promotion(db)


@router.post(
    "/promotion/{run_id}/undo",
    response_model=PromotionRunOut,
    summary="Отменить перевод",
    description="Восстанавливает состав классов и активность учеников из "
    "снапшота. Заблокировано (409), если после перевода уже создана кампания — "
    "откат сломал бы её состав. Созданные пустые классы не удаляются. Только админ.",
)
async def undo_promotion(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> PromotionRunOut:
    return await service.undo_promotion(db, run_id)


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


@router.post(
    "/{class_id}/teachers/detach",
    response_model=SchoolClassOut,
    summary="Открепить учителей от класса (bulk)",
    description="Открепить сразу нескольких учителей одним вызовом — зеркально "
    "bulk-привязке. Атомарно: если хоть кого-то из списка в классе нет, не "
    "открепляется никто (409). Классное руководство снимается вместе со "
    "связью. POST, а не DELETE, потому что тело у DELETE режут прокси. "
    "Только админ.",
)
async def remove_teachers_from_class(
    class_id: int,
    data: RemoveTeachersIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.remove_teachers_from_class(db, class_id, data.teacher_ids)


@router.post(
    "/{class_id}/students/detach",
    response_model=SchoolClassOut,
    summary="Открепить учеников от класса (bulk)",
    description="Открепить сразу нескольких учеников одним вызовом. Атомарно: "
    "если хоть кто-то из списка в классе не числится, не открепляется никто "
    "(409). Ученики остаются в системе, снапшоты класса в анкетах не меняются. "
    "Для массового перевода используйте привязку к новому классу — она "
    "перезаписывает старый. Только админ.",
)
async def remove_students_from_class(
    class_id: int,
    data: RemoveStudentsIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    return await service.remove_students_from_class(db, class_id, data.student_ids)


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
