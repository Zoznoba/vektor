# HTTP-слой users: «кто я», админский список, связь родитель—ребёнок.

from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.config import settings
from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.auth.schemas import UserOut
from vektor.modules.classes.models import SchoolClass
from vektor.modules.users import service
from vektor.modules.users.models import User
from vektor.modules.users.schemas import (
    AssignChildrenIn,
    BulkCreateIn,
    BulkCreateOut,
    MeOut,
    ParentWithChildrenOut,
)
from vektor.shared.academic_year import academic_year_label
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=MeOut,
    summary="Текущий пользователь",
    description="Профиль пользователя по токену авторизации, плюс класс и "
    "учебный год для шапки дашборда.",
)
async def read_me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeOut:
    # Класс нужен дашборду в шапке («8-1 класс»). Отдельным запросом, а не
    # relationship на UserOut: UserOut уходит ещё в списки и вложенные схемы,
    # где класс не нужен, а ленивая подгрузка там дала бы MissingGreenlet.
    school_class = None
    if user.school_class_id is not None:
        school_class = await db.get(SchoolClass, user.school_class_id)
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        class_label=f"{school_class.grade}-{school_class.section}" if school_class else None,
        academic_year=academic_year_label(date.today()),
    )


@router.get(
    "",
    response_model=list[UserOut],
    summary="Список пользователей",
    description="Все пользователи школы. Только админ.",
)
async def get_all_users(
    _admin_user: User = Depends(require_role(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)
):
    all_users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return all_users


@router.post(
    "/bulk",
    response_model=BulkCreateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Массовая загрузка пользователей",
    description="Завести пачку пользователей одним вызовом; опциональный "
    "`class_id` разом привязывает всех `role=student` к классу. Атомарно — "
    "любая ошибка (дубль внутри пачки, занятый email, нет класса) откатывает "
    "всю пачку. ВРЕМЕННО: всем ставится общий пароль из настроек, он же "
    "возвращается в ответе. Только админ.",
)
async def bulk_create_users(
    data: BulkCreateIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> BulkCreateOut:
    created = await service.bulk_create_users(db, data.users, data.class_id)

    return BulkCreateOut(
        created=created,
        class_id=data.class_id,
        default_password=settings.bulk_default_password,
    )


@router.get(
    "/{user_id}/children",
    response_model=list[UserOut],
    summary="Дети родителя",
    description="Список детей, привязанных к пользователю с ролью PARENT. Только админ.",
)
async def get_children(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[UserOut]:
    parent = await service.get_parent_with_children(db, user_id)
    return parent.children


@router.post(
    "/{user_id}/children",
    response_model=ParentWithChildrenOut,
    summary="Привязать детей к родителю",
    description="Массово и идемпотентно привязать учеников к родителю "
    "(повторная привязка — no-op). Цель — только PARENT, дети — только "
    "STUDENT, иначе 409. Только админ.",
)
async def assign_children_to_parent(
    user_id: int,
    data: AssignChildrenIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> ParentWithChildrenOut:
    return await service.assign_children(db, user_id, data.child_ids)
