# HTTP-слой auth. Тонкий: распаковать вход → вызвать service → упаковать выход.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.core.security import create_access_token
from vektor.modules.auth import service
from vektor.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def user_register(data: RegisterIn, db: AsyncSession = Depends(get_db)) -> UserOut:
    try:
        user = await service.register_user(db, data)
    except service.EmailAlreadyRegistered as err:
        raise HTTPException(status.HTTP_409_CONFLICT) from err
    return user


@router.post("/login", response_model=TokenOut)
async def user_login(data: LoginIn, db: AsyncSession = Depends(get_db)) -> TokenOut:
    user = await service.authenticate_user(db, data.email, data.password)
    if user is not None:
        return TokenOut(access_token=create_access_token(str(user.id)))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль"
    )
