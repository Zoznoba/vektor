# Бизнес-логика classes. Права назначает только админ — эта проверка уже
# сделана на уровне роутера (require_role(ADMIN)), здесь её дублировать не надо.

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.errors import DomainError
from vektor.modules.classes.models import SchoolClass, TeacherClass
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole


class ClassAlreadyExists(DomainError):
    """Класс с таким grade+section уже существует."""

    status_code = 409
    code = "class_already_exists"
    message = "Класс с таким номером уже существует"


class UserNotFound(DomainError):
    """Один или несколько пользователей с такими id не найдены."""

    status_code = 404
    code = "user_not_found"
    message = "Пользователь не найден"


class ClassNotFound(DomainError):
    """Класс с таким id не найден."""

    status_code = 404
    code = "class_not_found"
    message = "Класс не найден"


class TeacherAlreadyAssigned(DomainError):
    """Один или несколько учителей уже привязаны к этому классу."""

    status_code = 409
    code = "teacher_already_assigned"
    message = "Учитель уже привязан к этому классу"


class WrongRole(DomainError):
    """Роль пользователя не подходит для операции."""

    status_code = 409
    code = "wrong_role"
    message = "Роль пользователя не подходит для операции"


class TeacherNotInClass(DomainError):
    """Учитель не привязан к этому классу — нечего править или откреплять."""

    status_code = 404
    code = "teacher_not_in_class"
    message = "Учитель не привязан к этому классу"


class StudentNotInClass(DomainError):
    """Ученик числится не в этом классе — открепление относится не к нему."""

    status_code = 404
    code = "student_not_in_class"
    message = "Ученик не числится в этом классе"


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
    """Открепить учителя от класса. Классное руководство снимается вместе со
    связью — отдельно «разжаловать» перед откреплением не нужно."""
    school_class = await _load_class(db, class_id)
    link = _find_link(school_class, teacher_id)

    school_class.teacher_links.remove(link)  # delete-orphan удалит строку
    await db.commit()
    return await _load_class(db, class_id)


async def remove_student_from_class(
    db: AsyncSession, class_id: int, student_id: int
) -> SchoolClass:
    """Открепить ученика от класса: `school_class_id = None`.

    Ученик остаётся в системе со всей историей — анкеты хранят снапшот класса
    (`Assessment.subject_class_id`, Этап 5e), поэтому прошлые результаты
    открепление не меняет. Перевод в другой класс делается не этим вызовом, а
    assign_students на новый класс: у ученика класс один, и присвоение
    перезаписывает старый.
    """
    school_class = await _load_class(db, class_id)

    student = await db.get(User, student_id)
    if student is None:
        raise UserNotFound(f"Пользователь {student_id} не найден")
    if student.school_class_id != class_id:
        raise StudentNotInClass(f"Ученик {student_id} не числится в классе {class_id}")

    student.school_class_id = None
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
