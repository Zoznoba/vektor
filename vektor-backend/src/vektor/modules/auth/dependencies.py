# Зависимости аутентификации: «кто прислал запрос» и «пускать ли его».
#
# Цепочка: HTTPBearer достаёт токен из заголовка Authorization →
# get_current_user превращает токен в объект User (или 401) →
# require_role(...) проверяет роль (или 403).
#
# 401 = «я не знаю, кто ты» (нет/битый/просроченный токен)
# 403 = «я знаю, кто ты, но тебе сюда нельзя» (не та роль)
# Их важно не путать.

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.core.security import decode_access_token
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

# auto_error=False: если заголовка нет, credentials будет None и мы сами
# отдадим аккуратный 401 (иначе FastAPI отдаёт 403 — семантически неверно).
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            headers={"WWW-Authenticate": "Bearer"},
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No credentials provided",
        )
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            headers={"WWW-Authenticate": "Bearer"},
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT Invalid Token",
        ) from err
    user = await db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            headers={"WWW-Authenticate": "Bearer"},
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User unavaiable",
        )
    return user


# router usage Depends(require_role(UserRole.ADMIN, UserRole.TEACHER)
def require_role(*allowed: UserRole):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role in allowed:
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    return checker
