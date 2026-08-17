from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.core.rate_limit import rate_limit
from vektor.core.security import create_access_token
from vektor.modules.auth import service
from vektor.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Ограничение частоты стоит только здесь: перебор паролей и массовое создание
# учёток — единственные места, где повторяющийся запрос сам по себе является
# атакой. На прохождение анкет лимит не вешаем, там частые запросы штатны.
_login_limit = rate_limit("login", "login_rate_limit", "login_rate_window_seconds")
_register_limit = rate_limit("register", "register_rate_limit", "register_rate_window_seconds")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def user_register(
    data: RegisterIn, db: AsyncSession = Depends(get_db), _limit=_register_limit
) -> UserOut:
    user = await service.register_user(db, data)
    return user


@router.post("/login", response_model=TokenOut)
async def user_login(
    data: LoginIn, db: AsyncSession = Depends(get_db), _limit=_login_limit
) -> TokenOut:
    user = await service.authenticate_user(db, data.email, data.password)
    if user is not None:
        return TokenOut(access_token=create_access_token(str(user.id)))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль"
    )
