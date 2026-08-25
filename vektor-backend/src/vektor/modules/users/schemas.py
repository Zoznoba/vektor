# Pydantic-схемы users, которых нет в auth: связь родитель—ребёнок
# и массовая загрузка пользователей (Этап 3.7).

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import UserRole


class AssignChildrenIn(BaseModel):
    child_ids: list[int]


class SetUserActiveIn(BaseModel):
    is_active: bool


class ResetPasswordOut(BaseModel):
    """Новый пароль — эхом один раз, как default_password в BulkCreateOut:
    другого способа его узнать не будет, рассылки почтой в системе пока нет."""

    new_password: str


# ── Массовая загрузка (bulk) ──────────────────────────────────────────────
# Пароль в строке НЕ принимаем. ВРЕМЕННО (для тестов) всем создаваемым юзерам
# ставится один общий пароль из настроек (settings.bulk_default_password).
# Позже он сменится на авто-генерацию у каждого + рассылку — тогда сюда
# вернётся поле password в CreatedUserOut, а из ответа общий пароль уйдёт.
# Валидация email/длины имени — как в RegisterIn.


class BulkUserIn(BaseModel):
    """Одна строка выгрузки: кого завести. Без пароля — он общий (см. выше)."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole


class BulkCreateIn(BaseModel):
    """Тело запроса на массовое создание.

    class_id опционален: если задан, все строки с role=student разом
    привязываются к этому классу тем же вызовом (переиспользуем логику
    assign_students). Строки других ролей к классу не трогаем.
    """

    class_id: int | None = None
    users: list[BulkUserIn] = Field(min_length=1)


class BulkCreateOut(BaseModel):
    """Результат массового создания.

    default_password — тот самый общий пароль, эхом один раз, чтобы было чем
    залогиниться на тестах. ВРЕМЕННОЕ поле: уедет, когда включим генерацию
    и рассылку паролей по отдельности.
    """

    model_config = ConfigDict(from_attributes=True)

    created: list[UserOut]
    class_id: int | None = None
    default_password: str


class ParentWithChildrenOut(UserOut):
    """Родитель вместе со списком привязанных детей."""

    model_config = ConfigDict(from_attributes=True)

    children: list[UserOut]


class MeOut(UserOut):
    """/users/me — то же, что UserOut, плюс класс и учебный год для шапки
    дашборда.

    None у class_label — штатно: у учителя, родителя и админа класса нет.
    academic_year — не хранится нигде (период кампании — календарные год и
    месяц, а не учебный год: «2026-06» относится к 2025/2026), считается от
    текущей даты через
    shared/academic_year.py и относится к школе целиком, а не к пользователю.
    """

    class_label: str | None = None
    academic_year: str
