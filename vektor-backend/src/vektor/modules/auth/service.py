# Бизнес-логика auth. Ничего не знает про HTTP: ни Request, ни HTTPException.
# Ошибки домена — собственные исключения, роутер переведёт их в коды ответов.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.errors import DomainError
from vektor.core.security import hash_password, verify_password
from vektor.modules.auth.schemas import RegisterIn
from vektor.modules.users.models import User


class EmailAlreadyRegistered(DomainError):
    """Пользователь с таким email уже существует."""

    status_code = 409
    code = "email_already_registered"
    message = "Пользователь с таким email уже существует"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, data: RegisterIn) -> User:
    if await get_user_by_email(db, data.email) is not None:
        raise EmailAlreadyRegistered
    user = User(
        email=data.email,
        full_name=data.full_name,
        role=data.role,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is not None and verify_password(password, user.hashed_password):
        return user
    return None
