from pydantic import BaseModel, ConfigDict, Field

from vektor.modules.auth.schemas import UserOut


class TeacherInClassOut(BaseModel):
    """Учитель в составе класса вместе с атрибутами связи.

    Вложенный `teacher`, а не плоские поля поверх UserOut: subject и
    is_homeroom принадлежат ПАРЕ «учитель+класс», а не человеку — тот же
    учитель в другом классе ведёт другой предмет и может не быть кл. руком.
    """

    model_config = ConfigDict(from_attributes=True)

    teacher: UserOut
    subject: str | None
    is_homeroom: bool


class SchoolClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade: int
    section: str
    students: list[UserOut]
    # Источник — teacher_links (association object с subject/is_homeroom), а
    # НЕ одноимённый SchoolClass.teachers: тот отдаёт голых User и оставлен
    # для проверок прав в results/assessments. В JSON поле называется
    # `teachers` — фронту незачем знать про внутреннее имя связи.
    #
    # Кл. руководители отдельным списком не отдаются: это те же строки с
    # is_homeroom=true, и второй список пришлось бы держать в согласии с
    # первым. Фронт фильтрует по флагу.
    teachers: list[TeacherInClassOut] = Field(validation_alias="teacher_links")


class SchoolClassCreate(BaseModel):
    grade: int = Field(ge=1, le=11)
    section: str = Field(min_length=1, max_length=10)


class AssignStudentsIn(BaseModel):
    student_ids: list[int]


class AssignTeachersIn(BaseModel):
    teacher_ids: list[int]
    # Общие на всю пачку: назначают обычно предметника в класс либо сразу
    # руководителя. Точечная правка — PATCH по одному учителю.
    subject: str | None = Field(default=None, max_length=100)
    is_homeroom: bool = False


class UpdateTeacherInClassIn(BaseModel):
    """Частичная правка связи: роутер отдаёт в сервис только те поля, что
    реально пришли в теле (`exclude_unset`). Поэтому отсутствие ключа —
    «не трогать», а явный `"subject": null` — «стереть предмет». Иначе смена
    предмета сбрасывала бы руководство классом, и наоборот."""

    subject: str | None = Field(default=None, max_length=100)
    is_homeroom: bool | None = None
