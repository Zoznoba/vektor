from datetime import datetime

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
    # min_length=0: у 10 и 11 классов параллели нет — секция пустая, и фронтовый
    # classLabel подписывает такой класс просто «10». Импорт заводит их так же.
    section: str = Field(min_length=0, max_length=10)


class AssignStudentsIn(BaseModel):
    student_ids: list[int]


class AssignTeachersIn(BaseModel):
    teacher_ids: list[int]
    # Общие на всю пачку: назначают обычно предметника в класс либо сразу
    # руководителя. Точечная правка — PATCH по одному учителю.
    subject: str | None = Field(default=None, max_length=100)
    is_homeroom: bool = False


class RemoveStudentsIn(BaseModel):
    """Bulk-открепление учеников. Тело, а не список в пути, и POST, а не
    DELETE: тело у DELETE режут прокси и плохо поддерживают клиенты."""

    student_ids: list[int]


class RemoveTeachersIn(BaseModel):
    teacher_ids: list[int]


class UpdateTeacherInClassIn(BaseModel):
    """Частичная правка связи: роутер отдаёт в сервис только те поля, что
    реально пришли в теле (`exclude_unset`). Поэтому отсутствие ключа —
    «не трогать», а явный `"subject": null` — «стереть предмет». Иначе смена
    предмета сбрасывала бы руководство классом, и наоборот."""

    subject: str | None = Field(default=None, max_length=100)
    is_homeroom: bool | None = None


# ── Ежегодный перевод классов ─────────────────────────────────────────────


class PreviewPromotionIn(BaseModel):
    # source_class_id -> целевая секция (перебивает секцию по умолчанию —
    # на случай нестандартного перестроения параллелей).
    section_overrides: dict[int, str] = Field(default_factory=dict)


class ApplyPromotionIn(PreviewPromotionIn):
    # id исходных классов, чей состав учителей перенести в новый целевой
    # класс. Работает только для НЕ merge-переходов, где целевой класс
    # создаётся с нуля.
    carry_teachers_for: list[int] = Field(default_factory=list)
    # Должно точно совпасть с текущим ярлыком учебного года на сервере —
    # защита от случайного нажатия.
    confirm_academic_year: str


class TransitionOut(BaseModel):
    target_grade: int
    target_section: str
    target_label: str
    target_class_id: int | None
    source_class_ids: list[int]
    source_labels: list[str]
    moving_count: int
    already_in_target_count: int
    merge: bool


class GraduatingOut(BaseModel):
    class_id: int
    class_label: str
    student_count: int


class PromotionPlanOut(BaseModel):
    academic_year: str
    already_ran: bool
    transitions: list[TransitionOut]
    graduating: list[GraduatingOut]
    warnings: list[str]
    total_moving: int
    total_graduating: int
    classes_to_create: int


class PromotionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    academic_year: str
    ran_at: datetime
    summary: dict
    undone_at: datetime | None
    # false, если после перевода уже создана кампания (или он уже отменён).
    can_undo: bool
