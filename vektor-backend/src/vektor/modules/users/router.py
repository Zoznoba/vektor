# HTTP-слой users. Пока два эндпоинта — «кто я» и админский список.

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.auth.schemas import UserOut
from vektor.modules.users.models import User
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
