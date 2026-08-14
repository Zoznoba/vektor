from pydantic import BaseModel, ConfigDict


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    # Позиция внутри критерия (0..2). Возрастная условность сюда больше не
    # приходит: она свойство критерия, см. CompetencyOut.min_grade/max_grade.
    order: int


class OutcomeAreaOut(BaseModel):
    """«ОР / навык» — верхний уровень методики, группирует критерии."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    order: int


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None
    order: int
    # None — критерий без возрастных ограничений, показывается всем классам.
    min_grade: int | None
    max_grade: int | None
    outcome_area: OutcomeAreaOut
    questions: list[QuestionOut]
