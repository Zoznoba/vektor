# Бизнес-логика classes. Права назначает только админ — эта проверка уже
# сделана на уровне роутера (require_role(ADMIN)), здесь её дублировать не надо.

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.assessments.models import Campaign
from vektor.modules.classes.errors import (
    ClassAlreadyExists,
    ClassNotFound,
    PromotionAlreadyRun,
    PromotionAlreadyUndone,
    PromotionConfirmMismatch,
    PromotionRunNotFound,
    PromotionUndoBlocked,
    StudentNotInClass,
    TeacherAlreadyAssigned,
    TeacherNotInClass,
)
from vektor.modules.classes.models import PromotionRun, SchoolClass, TeacherClass
from vektor.modules.classes.promotion import (
    PromotionPlan,
    SchoolClassView,
    StudentView,
    plan_promotion,
)
from vektor.modules.classes.schemas import (
    GraduatingOut,
    PromotionPlanOut,
    PromotionRunOut,
    TransitionOut,
)
from vektor.modules.users.errors import UserNotFound, WrongRole
from vektor.modules.users.models import User
from vektor.shared.academic_year import academic_year_label
from vektor.shared.class_label import class_label
from vektor.shared.enums import UserRole

# Состав класса всегда возвращаем целиком: список учителей теперь идёт с
# атрибутами связи, и `teacher_links` без явной догрузки развалится на
# сериализации (MissingGreenlet) — та же грабля, что в Этапе 3.5.
_CLASS_LOAD = (
    selectinload(SchoolClass.students),
    selectinload(SchoolClass.teacher_links).selectinload(TeacherClass.teacher),
)


async def _load_class(db: AsyncSession, class_id: int) -> SchoolClass:
    """Класс со всем составом. Единственная точка загрузки — иначе каждый
    сервис заново решает, что догружать, и забывает про teacher_links."""
    # populate_existing обязателен: сессия живёт с expire_on_commit=False, и
    # без него объект вернётся из identity map с коллекциями, загруженными ДО
    # изменений — состав класса в ответе оказался бы прежним.
    result = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id == class_id)
        .options(*_CLASS_LOAD)
        .execution_options(populate_existing=True)
    )
    school_class = result.scalar_one_or_none()
    if school_class is None:
        raise ClassNotFound
    return school_class


async def create_class(db: AsyncSession, grade: int, section: str) -> SchoolClass:
    same_exist = await db.execute(
        select(SchoolClass).where(SchoolClass.grade == grade, SchoolClass.section == section)
    )
    if same_exist.scalar_one_or_none() is not None:
        raise ClassAlreadyExists
    school_class = SchoolClass(grade=grade, section=section)

    db.add(school_class)
    await db.commit()
    return await _load_class(db, school_class.id)


async def all_classes(db: AsyncSession) -> list[SchoolClass]:
    result = await db.execute(
        select(SchoolClass).options(*_CLASS_LOAD).order_by(SchoolClass.grade, SchoolClass.section)
    )
    return result.scalars().all()


async def assign_students(db: AsyncSession, class_id: int, student_ids: list[int]) -> SchoolClass:
    school_class = await _load_class(db, class_id)

    students_query = await db.execute(select(User).where(User.id.in_(student_ids)))
    students = students_query.scalars().all()

    found_ids = {u.id for u in students}
    missing_ids = set(student_ids) - found_ids
    if missing_ids:
        raise UserNotFound(f"Не найденные пользователи: {missing_ids}")

    for student in students:
        student.school_class_id = class_id

    await db.commit()
    return await _load_class(db, school_class.id)


async def assign_teachers(
    db: AsyncSession,
    class_id: int,
    teacher_ids: list[int],
    subject: str | None = None,
    is_homeroom: bool = False,
) -> SchoolClass:
    """Привязать учителей к классу одной пачкой.

    subject/is_homeroom общие на всю пачку: назначают либо предметника, либо
    сразу руководителя. Точечная правка — update_teacher_in_class.
    """
    school_class = await _load_class(db, class_id)
    teachers = await _load_teachers(db, teacher_ids)

    already_assigned_ids = {link.teacher_id for link in school_class.teacher_links}
    duplicated_ids = {t.id for t in teachers} & already_assigned_ids
    if duplicated_ids:
        raise TeacherAlreadyAssigned(f"Учителя уже прикреплены к классу: {duplicated_ids}")

    for teacher in teachers:
        school_class.teacher_links.append(
            TeacherClass(teacher_id=teacher.id, subject=subject, is_homeroom=is_homeroom)
        )

    await db.commit()
    return await _load_class(db, class_id)


async def update_teacher_in_class(
    db: AsyncSession, class_id: int, teacher_id: int, changes: dict[str, Any]
) -> SchoolClass:
    """Правка связи «учитель ↔ класс»: предмет и/или классное руководство.

    `changes` — только реально пришедшие поля (роутер собирает их через
    `exclude_unset`), поэтому `{"subject": None}` стирает предмет, а
    отсутствие ключа оставляет его как был.
    """
    school_class = await _load_class(db, class_id)
    link = _find_link(school_class, teacher_id)

    if "subject" in changes:
        link.subject = changes["subject"]
    if "is_homeroom" in changes and changes["is_homeroom"] is not None:
        link.is_homeroom = changes["is_homeroom"]

    await db.commit()
    return await _load_class(db, class_id)


async def remove_teacher_from_class(
    db: AsyncSession, class_id: int, teacher_id: int
) -> SchoolClass:
    """Открепить одного учителя — частный случай remove_teachers_from_class.

    Своей логики здесь нет намеренно: одиночный DELETE и bulk обязаны вести
    себя одинаково, а два пути с одинаковыми проверками разъезжаются.
    """
    return await remove_teachers_from_class(db, class_id, [teacher_id])


async def remove_teachers_from_class(
    db: AsyncSession, class_id: int, teacher_ids: list[int]
) -> SchoolClass:
    """Открепить учителей от класса (bulk). Классное руководство снимается
    вместе со связью — отдельно «разжаловать» перед откреплением не нужно.

    Вся пачка проверяется ДО записи, зеркально assign_teachers: падение на
    середине оставило бы состав разобранным наполовину. Открепление, в отличие
    от привязки, НЕ идемпотентно — учитель, которого в классе нет, значит, что
    выделение на экране разошлось с реальным составом, и молчать об этом
    нельзя.
    """
    school_class = await _load_class(db, class_id)

    if not teacher_ids:
        return school_class

    # dict.fromkeys — дедупликация с сохранением порядка: повторный id в теле
    # иначе уронил бы list.remove на второй попытке.
    links = [_find_link(school_class, teacher_id) for teacher_id in dict.fromkeys(teacher_ids)]

    for link in links:
        school_class.teacher_links.remove(link)  # delete-orphan удалит строку
    await db.commit()
    return await _load_class(db, class_id)


async def remove_student_from_class(
    db: AsyncSession, class_id: int, student_id: int
) -> SchoolClass:
    """Открепить одного ученика — частный случай remove_students_from_class.

    Ученик остаётся в системе со всей историей — анкеты хранят снапшот класса
    (`Assessment.subject_class_id`, Этап 5e), поэтому прошлые результаты
    открепление не меняет. Перевод в другой класс делается не этим вызовом, а
    assign_students на новый класс: у ученика класс один, и присвоение
    перезаписывает старый.
    """
    return await remove_students_from_class(db, class_id, [student_id])


async def remove_students_from_class(
    db: AsyncSession, class_id: int, student_ids: list[int]
) -> SchoolClass:
    """Открепить учеников от класса (bulk): `school_class_id = None`.

    Атомарность и неидемпотентность — те же, что в remove_teachers_from_class.
    """
    school_class = await _load_class(db, class_id)

    if not student_ids:
        return school_class

    found = await db.execute(select(User).where(User.id.in_(set(student_ids))))
    students = {student.id: student for student in found.scalars()}

    for student_id in student_ids:
        student = students.get(student_id)
        if student is None:
            raise UserNotFound(f"Пользователь {student_id} не найден")
        if student.school_class_id != class_id:
            raise StudentNotInClass(f"Ученик {student_id} не числится в классе {class_id}")

    for student_id in student_ids:
        students[student_id].school_class_id = None

    await db.commit()
    return await _load_class(db, school_class.id)


async def _load_teachers(db: AsyncSession, teacher_ids: list[int]) -> list[User]:
    """Учителя по id: все должны существовать и все — быть учителями."""
    result = await db.execute(select(User).where(User.id.in_(teacher_ids)))
    teachers = result.scalars().all()

    missing_ids = set(teacher_ids) - {t.id for t in teachers}
    if missing_ids:
        raise UserNotFound(f"Не найдены пользователи: {missing_ids}")

    wrong = [t for t in teachers if t.role != UserRole.TEACHER]
    if wrong:
        raise WrongRole(f"Не учителя: {[t.id for t in wrong]}")
    return list(teachers)


def _find_link(school_class: SchoolClass, teacher_id: int) -> TeacherClass:
    for link in school_class.teacher_links:
        if link.teacher_id == teacher_id:
            return link
    raise TeacherNotInClass(f"Учитель {teacher_id} не привязан к классу {school_class.id}")


# ── Ежегодный перевод классов ────────────────────────────────────────────
#
# Доменное правило — в classes/promotion.py (чистая plan_promotion, без БД).
# Здесь: загрузка состава для неё, применение плана одной транзакцией,
# маркер-и-откат через PromotionRun. Смена User.school_class_id не трогает
# снапшоты Assessment — прошлая диагностика остаётся на месте.


async def _load_school_views(db: AsyncSession) -> list[SchoolClassView]:
    result = await db.execute(select(SchoolClass).options(selectinload(SchoolClass.students)))
    return [
        SchoolClassView(
            id=c.id,
            grade=c.grade,
            section=c.section,
            students=tuple(StudentView(id=s.id, is_active=s.is_active) for s in c.students),
        )
        for c in result.scalars()
    ]


async def _active_run(db: AsyncSession, academic_year: str) -> PromotionRun | None:
    result = await db.execute(
        select(PromotionRun).where(
            PromotionRun.academic_year == academic_year,
            PromotionRun.undone_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _has_campaign_since(db: AsyncSession, since) -> bool:
    result = await db.execute(select(Campaign.id).where(Campaign.created_at > since).limit(1))
    return result.first() is not None


def _plan_to_out(
    plan: PromotionPlan, academic_year: str, already_ran: bool, labels: dict[int, str]
) -> PromotionPlanOut:
    return PromotionPlanOut(
        academic_year=academic_year,
        already_ran=already_ran,
        transitions=[
            TransitionOut(
                target_grade=t.target_grade,
                target_section=t.target_section,
                target_label=class_label(t.target_grade, t.target_section),
                target_class_id=t.target_class_id,
                source_class_ids=list(t.source_class_ids),
                source_labels=[labels.get(cid, str(cid)) for cid in t.source_class_ids],
                moving_count=len(t.moving_student_ids),
                already_in_target_count=len(t.already_in_target_ids),
                merge=t.merge,
            )
            for t in plan.transitions
        ],
        graduating=[
            GraduatingOut(
                class_id=g.class_id,
                class_label=labels.get(g.class_id, str(g.class_id)),
                student_count=len(g.student_ids),
            )
            for g in plan.graduating
        ],
        warnings=list(plan.warnings),
        total_moving=plan.total_moving,
        total_graduating=plan.total_graduating,
        classes_to_create=plan.classes_to_create,
    )


async def preview_promotion(
    db: AsyncSession, section_overrides: dict[int, str]
) -> PromotionPlanOut:
    year = academic_year_label(date.today())
    views = await _load_school_views(db)
    plan = plan_promotion(views, section_overrides)
    labels = {v.id: class_label(v.grade, v.section) for v in views}
    already = await _active_run(db, year) is not None
    return _plan_to_out(plan, year, already, labels)


async def apply_promotion(
    db: AsyncSession,
    section_overrides: dict[int, str],
    carry_teachers_for: list[int],
    confirm_academic_year: str,
    current_user: User,
) -> PromotionRunOut:
    year = academic_year_label(date.today())
    if confirm_academic_year.strip() != year:
        raise PromotionConfirmMismatch
    if await _active_run(db, year) is not None:
        raise PromotionAlreadyRun

    views = await _load_school_views(db)
    plan = plan_promotion(views, section_overrides)

    affected: set[int] = set()
    for t in plan.transitions:
        affected.update(t.moving_student_ids)
    for g in plan.graduating:
        affected.update(g.student_ids)

    users_result = await db.execute(select(User).where(User.id.in_(affected)))
    users_by_id = {u.id: u for u in users_result.scalars()}

    snapshot = [
        {
            "user_id": uid,
            "old_class_id": user.school_class_id,
            "was_active": user.is_active,
        }
        for uid, user in users_by_id.items()
    ]

    carry = set(carry_teachers_for)
    classes_created = 0

    for t in plan.transitions:
        target_id = t.target_class_id
        if target_id is None:
            new_class = SchoolClass(grade=t.target_grade, section=t.target_section)
            db.add(new_class)
            await db.flush()
            target_id = new_class.id
            classes_created += 1

            # Перенос учителей только для нового целевого без слияния: у merge
            # несколько исходных составов, чей брать — решать не нам.
            if not t.merge and t.source_class_ids[0] in carry:
                source_id = t.source_class_ids[0]
                links = await db.execute(
                    select(TeacherClass).where(TeacherClass.class_id == source_id)
                )
                for link in links.scalars():
                    db.add(
                        TeacherClass(
                            teacher_id=link.teacher_id,
                            class_id=target_id,
                            subject=link.subject,
                            is_homeroom=link.is_homeroom,
                        )
                    )

        for student_id in t.moving_student_ids:
            users_by_id[student_id].school_class_id = target_id

    for g in plan.graduating:
        for student_id in g.student_ids:
            user = users_by_id[student_id]
            user.is_active = False
            user.school_class_id = None

    run = PromotionRun(
        academic_year=year,
        ran_by_id=current_user.id,
        summary={
            "moved": plan.total_moving,
            "graduated": plan.total_graduating,
            "classes_created": classes_created,
        },
        snapshot=snapshot,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return PromotionRunOut(**_run_fields(run), can_undo=True)


async def current_promotion(db: AsyncSession) -> PromotionRunOut | None:
    year = academic_year_label(date.today())
    run = await _active_run(db, year)
    if run is None:
        return None
    can_undo = not await _has_campaign_since(db, run.ran_at)
    return PromotionRunOut(**_run_fields(run), can_undo=can_undo)


async def undo_promotion(db: AsyncSession, run_id: int) -> PromotionRunOut:
    run = await db.get(PromotionRun, run_id)
    if run is None:
        raise PromotionRunNotFound
    if run.undone_at is not None:
        raise PromotionAlreadyUndone
    if await _has_campaign_since(db, run.ran_at):
        raise PromotionUndoBlocked

    for entry in run.snapshot:
        user = await db.get(User, entry["user_id"])
        if user is None:
            continue
        user.school_class_id = entry["old_class_id"]
        user.is_active = entry["was_active"]

    run.undone_at = func.now()
    await db.commit()
    await db.refresh(run)
    return PromotionRunOut(**_run_fields(run), can_undo=False)


def _run_fields(run: PromotionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "academic_year": run.academic_year,
        "ran_at": run.ran_at,
        "summary": run.summary,
        "undone_at": run.undone_at,
    }
