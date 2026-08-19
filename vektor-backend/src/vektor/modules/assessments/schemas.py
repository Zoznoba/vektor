# Pydantic-схемы assessments. Вход — что клиент имеет право прислать,
# выход — что мы готовы показать.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import AssessmentStatus, CampaignStatus


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    period: str = Field(min_length=1, max_length=20)
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    period: str
    status: CampaignStatus
    opens_at: datetime | None
    closes_at: datetime | None
    created_at: datetime


class GenerateIn(BaseModel):
    class_ids: list[int] = Field(min_length=1)
    # Оценивают ли одноклассники друг друга. По умолчанию нет — только
    # самооценка + учителя + родители. True добавляет пиров (student→classmate).
    include_peers: bool = False


class GenerateResult(BaseModel):
    created: int
    campaign: CampaignOut


class QuestionForAssessmentOut(BaseModel):
    id: int
    competency_id: int
    text: str
    order: int
    is_conditional: bool
    value: int | None


class AssessmentDetailOut(BaseModel):
    id: int
    campaign_id: int
    subject: UserOut
    questions: list[QuestionForAssessmentOut]


class AssessmentListItemOut(BaseModel):
    id: int
    campaign_id: int
    campaign_title: str
    campaign_period: str
    campaign_closes_at: datetime | None
    subject: UserOut
    is_self: bool
    status: AssessmentStatus
    answered_questions: int
    total_questions: int


class AnswerIn(BaseModel):
    question_id: int
    value: int = Field(ge=1, le=5)


class SubmitAnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1)


class SubmitResult(BaseModel):
    # Ложится на фронтовый PendingSurvey: answered_questions ↔ answeredQuestions,
    # total_questions ↔ totalQuestions.
    assessment_id: int
    status: AssessmentStatus
    answered_questions: int
    total_questions: int
