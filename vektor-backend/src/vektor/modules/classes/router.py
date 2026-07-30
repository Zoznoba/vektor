from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("", response_model=SchoolClassOut, status_code=status.HTTP_201_CREATED)
async def create_school_class(
    data: SchoolClassCreate,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    try:
        return await service.create_class(db=db, grade=data.grade, section=data.section)
    except service.ClassAlreadyExists as err:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.get("", response_model=list[SchoolClassOut])
async def all_school_classes(
    db: AsyncSession = Depends(get_db),
    _roles=Depends(require_role(UserRole.ADMIN, UserRole.TEACHER)),
) -> list[SchoolClassOut]:
    return await service.all_classes(db)


@router.post("/{class_id}/students", response_model=SchoolClassOut)
async def assign_students_to_class(
    class_id: int,
    data: AssignStudentsIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    try:
        return await service.assign_students(db, class_id, data.student_ids)
    except service.ClassNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Класс не найден") from err
    except service.UserNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(err)) from err


@router.post("/{class_id}/teachers", response_model=SchoolClassOut)
async def assign_teachers_to_class(
    class_id: int,
    data: AssignTeachersIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    try:
        return await service.assign_teachers(db, class_id, data.teacher_ids)
    except service.ClassNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Класс не найден") from err
    except service.UserNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except service.TeacherAlreadyAssigned as err:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err


@router.put("/{class_id}/homeroom", response_model=SchoolClassOut)
async def assign_homeroom_teacher(
    class_id: int,
    data: AssignHomeroomIn,
    db: AsyncSession = Depends(get_db),
    _admin_role=Depends(require_role(UserRole.ADMIN)),
) -> SchoolClassOut:
    try:
        return await service.assign_homeroom(db, class_id, data.teacher_id)
    except service.ClassNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Класс не найден") from err
    except service.UserNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except service.WrongRole as err:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err
