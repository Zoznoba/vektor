# HTTP-слой users: «кто я», админский список, связь родитель—ребёнок.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.auth.schemas import UserOut
from vektor.modules.users import service
from vektor.modules.users.models import User
from vektor.modules.users.schemas import AssignChildrenIn, ParentWithChildrenOut
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_me(user: User = Depends(get_current_user)) -> UserOut:
    return user


@router.get("", response_model=list[UserOut])
async def get_all_users(
    _admin_user: User = Depends(require_role(UserRole.ADMIN)), db: AsyncSession = Depends(get_db)
):
    all_users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return all_users


@router.get("/{user_id}/children", response_model=list[UserOut])
async def get_children(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> list[UserOut]:
    try:
        parent = await service.get_parent_with_children(db, user_id)
    except service.UserNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except service.WrongRole as err:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err
    return parent.children


@router.post("/{user_id}/children", response_model=ParentWithChildrenOut)
async def assign_children_to_parent(
    user_id: int,
    data: AssignChildrenIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> ParentWithChildrenOut:
    try:
        return await service.assign_children(db, user_id, data.child_ids)
    except service.UserNotFound as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    except service.WrongRole as err:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err
