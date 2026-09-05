# Pydantic-схемы auth: контракт между HTTP и сервисом.
#
# Схема входа (RegisterIn) и схема выхода (UserOut) — разные классы,
# даже если поля похожи. Вход: то, что клиент ИМЕЕТ ПРАВО прислать.
# Выход: то, что мы ГОТОВЫ показать. hashed_password не должен оказаться
# ни там, ни там.

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from vektor.shared.enums import UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "student@vektor.ru",
                "password": "correct-horse",
                "full_name": "Иванова Полина",
                "role": "student",
            }
        }
    )


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    # Кейс отдаём ИДЕНТИФИКАТОРОМ, а не названием: это обычная колонка, её
    # видно без дозагрузки связи, тогда как name потребовал бы selectinload в
    # каждом месте, где UserOut собирается из ORM-объекта (а таких мест
    # десяток) — и первое же забытое дало бы MissingGreenlet. Название кейса
    # экраны и так знают из /cases; человеку в шапке его отдаёт /users/me.
    case_id: int | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "student@vektor.ru", "password": "correct-horse"}}
    )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
