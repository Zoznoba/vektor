# Бизнес-логика classes. Права назначает только админ — эта проверка уже
# сделана на уровне роутера (require_role(ADMIN)), здесь её дублировать не надо.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.classes.models import SchoolClass
from vektor.modules.users.models import User


class ClassAlreadyExists(Exception):
    """Класс с таким grade+section уже существует."""


class UserNotFound(Exception):
    """Один или несколько пользователей с такими id не найдены."""


class ClassNotFound(Exception):
    """Класс с таким id не найден."""


class TeacherAlreadyAssigned(Exception):
    """Один или несколько учителей уже привязаны к этому классу."""


async def create_class(db: AsyncSession, grade: int, section: str) -> SchoolClass:
    same_exist = await db.execute(
        select(SchoolClass).where(SchoolClass.grade == grade, SchoolClass.section == section)
    )
    if same_exist.scalar_one_or_none() is not None:
        raise ClassAlreadyExists
    school_class = SchoolClass(grade=grade, section=section)

    db.add(school_class)
    await db.commit()
    await db.refresh(school_class, attribute_names=["students", "teachers"])
    return school_class


async def all_classes(db: AsyncSession) -> list[SchoolClass]:
    result = await db.execute(
        select(SchoolClass).options(
            selectinload(SchoolClass.teachers), selectinload(SchoolClass.students)
        )
    )
    return result.scalars().all()


async def assign_students(db: AsyncSession, class_id: int, student_ids: list[int]) -> SchoolClass:

    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise ClassNotFound

    students_query = await db.execute(select(User).where(User.id.in_(student_ids)))
    students = students_query.scalars().all()

    found_ids = {u.id for u in students}
    missing_ids = set(student_ids) - found_ids
    if missing_ids:
        raise UserNotFound(f"Не найденные пользователи: {missing_ids}")

    for student in students:
        student.school_class_id = class_id

    await db.commit()
    await db.refresh(school_class, attribute_names=["students", "teachers"])
    return school_class


async def assign_teachers(db: AsyncSession, class_id: int, teacher_ids: list[int]) -> SchoolClass:
    school_class_query = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id == class_id)
        .options(selectinload(SchoolClass.teachers))
    )
    school_class = school_class_query.scalar_one_or_none()
    if school_class is None:
        raise ClassNotFound

    teachers_query = await db.execute(select(User).where(User.id.in_(teacher_ids)))
    teachers = teachers_query.scalars().all()
    found_ids = {u.id for u in teachers}
    missing_ids = set(teacher_ids) - found_ids
    if missing_ids:
        raise UserNotFound(f"Не найдены пользователи: {missing_ids}")

    already_assigned_ids = {t.id for t in school_class.teachers}
    duplicated_ids = found_ids & already_assigned_ids
    if duplicated_ids:
        raise TeacherAlreadyAssigned(f"Учителя уже прикреплены к классу: {duplicated_ids}")

    school_class.teachers.extend(teachers)
    await db.commit()
    await db.refresh(school_class, attribute_names=["students", "teachers"])
    return school_class
