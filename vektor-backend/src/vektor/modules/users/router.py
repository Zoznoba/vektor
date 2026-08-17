# HTTP-слой users: «кто я», админский список, связь родитель—ребёнок.

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
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeOut)
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
    )


@router.get("", response_model=list[UserOut])
async def get_all_users(
    _admin_user: User = Depends(require_role(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)
):
    all_users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return all_users


@router.post("/bulk", response_model=BulkCreateOut, status_code=status.HTTP_201_CREATED)
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


@router.get("/{user_id}/children", response_model=list[UserOut])
async def get_children(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[UserOut]:
    parent = await service.get_parent_with_children(db, user_id)
    return parent.children


@router.post("/{user_id}/children", response_model=ParentWithChildrenOut)
async def assign_children_to_parent(
    user_id: int,
    data: AssignChildrenIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> ParentWithChildrenOut:
    return await service.assign_children(db, user_id, data.child_ids)
