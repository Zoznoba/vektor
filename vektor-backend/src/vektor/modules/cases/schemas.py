from pydantic import BaseModel, ConfigDict, Field

from vektor.modules.auth.schemas import UserOut


class CaseOut(BaseModel):
    """Кейс с полным составом.

    Учеников и учителей отдаём ДВУМЯ отдельными списками, а не одним
    `members` с ролью внутри: на экране это две разные вкладки, и фронту
    иначе пришлось бы фильтровать по роли в каждом месте. Здесь это дёшево —
    источники students/teachers уже разделены на уровне модели.

    Атрибутов у связи нет (в отличие от TeacherInClassOut с subject/is_homeroom):
    предмет учителя принадлежит паре «учитель+класс», а кейс сам по себе и есть
    профильная деятельность.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    students: list[UserOut]
    teachers: list[UserOut]


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)


class CaseUpdate(BaseModel):
    """Частичная правка — та же схема работы, что UpdateTeacherInClassIn
    (classes/schemas.py:56): роутер отдаёт в сервис только реально пришедшие
    поля через `model_dump(exclude_unset=True)`, поэтому отсутствие ключа
    означает «не трогать», а явный `"description": null` — «стереть».
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)


class AssignMembersIn(BaseModel):
    """Bulk-привязка, как AssignStudentsIn/AssignTeachersIn у классов: одним
    вызовом список id, а не по одному человеку за раз."""

    user_ids: list[int]
