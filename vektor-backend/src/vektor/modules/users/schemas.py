# Pydantic-схемы users, которых нет в auth: связь родитель—ребёнок
# и массовая загрузка пользователей (Этап 3.7).

from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import UserRole


class AssignChildrenIn(BaseModel):
    child_ids: list[int]


class UserUpdateIn(BaseModel):
    """Правка анкетных данных человека админом.

    Частичная: сервис получает только реально пришедшие поля
    (`model_dump(exclude_unset=True)` в роутере), поэтому отсутствие ключа —
    «не трогать», а явный `"birth_date": null` — «стереть дату». Тот же
    приём, что у PATCH предметной роли учителя в классе (7m).

    Чего здесь НЕТ и почему:
    - `role` — от неё зависит всё: кто кого оценивает, чьи ответы попадают в
      слой teacher/parent, кому виден класс. Уже собранные анкеты при смене
      роли не переписываются (роль ратора — снапшот, Этап 5a), и человек
      оказался бы наполовину в прошлой роли. Заводится заново, а старая
      учётка деактивируется.
    - `is_active` — у него свой эндпоинт с защитой от самоблокировки
      (`PATCH /users/{id}/active`), и дублировать её здесь значило бы держать
      два места в согласии.
    - класс и кейс — правятся со своих экранов, там же, где видно состав
      целиком; здесь они были бы вторым способом сделать то же самое.
    """

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    birth_date: date | None = None

    @field_validator("email", "full_name")
    @classmethod
    def _reject_explicit_null(cls, value: str | None) -> str:
        """`null` стирает значение — и это осмысленно только для даты
        рождения. Без email нельзя войти, без имени человека не найти, так
        что явный null здесь — ошибка клиента, а не «стереть». Валидатор
        срабатывает только на реально присланном поле: значения по умолчанию
        pydantic не валидирует.
        """
        if value is None:
            raise ValueError("Поле нельзя стереть — пришлите значение или не присылайте ключ")
        return value


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

    case_id — то же для кейса, но с одним отличием: в кейс попадают И ученики,
    И учителя, потому что членство в кейсе одно на обе роли (FK users.case_id,
    Этап 8). Родителей и админов не трогаем — их в кейсе не бывает.
    """

    class_id: int | None = None
    case_id: int | None = None
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
    case_id: int | None = None
    default_password: str


class ParentWithChildrenOut(UserOut):
    """Родитель вместе со списком привязанных детей."""

    model_config = ConfigDict(from_attributes=True)

    children: list[UserOut]


class MeOut(UserOut):
    """/users/me — то же, что UserOut, плюс класс, кейс и учебный год для
    шапки дашборда.

    None у class_label — штатно: у учителя, родителя и админа класса нет.
    None у case_name — тем более штатно: кейс есть у меньшинства (профильная
    группа — это кружок, а не обязательная для всех единица).
    academic_year — не хранится нигде (период кампании — календарные год и
    месяц, а не учебный год: «2026-06» относится к 2025/2026), считается от
    текущей даты через
    shared/academic_year.py и относится к школе целиком, а не к пользователю.
    """

    class_label: str | None = None
    case_name: str | None = None
    academic_year: str
