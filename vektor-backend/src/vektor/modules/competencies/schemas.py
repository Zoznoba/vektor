from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vektor.shared.enums import QuestionnaireVersionStatus


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


# ---------------------------------------------------------------------------
# Конструктор анкеты (Этап 7): черновик редакции, CRUD глав/критериев/
# вопросов, публикация. См. competencies/service.py и models.py — там же
# объяснение, почему OutcomeArea/Competency не версионируются, а Question да.
# ---------------------------------------------------------------------------


class QuestionnaireVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str
    note: str | None
    status: QuestionnaireVersionStatus
    is_current: bool
    created_at: datetime


class BuilderQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    order: int


class BuilderCompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    order: int
    min_grade: int | None
    max_grade: int | None
    is_archived: bool
    is_draft: bool
    questions: list[BuilderQuestionOut]


class BuilderOutcomeAreaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    order: int
    is_archived: bool
    is_draft: bool
    competencies: list[BuilderCompetencyOut]


class QuestionnaireTreeOut(BaseModel):
    version: QuestionnaireVersionOut
    outcome_areas: list[BuilderOutcomeAreaOut]


class OutcomeAreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CompetencyIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    # None — критерий без возрастных ограничений, см. Competency.min_grade.
    min_grade: int | None = Field(default=None, ge=1, le=11)
    max_grade: int | None = Field(default=None, ge=1, le=11)


class QuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ArchiveIn(BaseModel):
    is_archived: bool


class MoveIn(BaseModel):
    direction: Literal["up", "down"]
