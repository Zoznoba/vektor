# Pydantic-схемы assessments. Вход — что клиент имеет право прислать,
# выход — что мы готовы показать.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import AssessmentStatus, CampaignStatus, RaterRole


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    # Период — год + месяц числами. Месяц как НАЗВАНИЕ («Июнь») — это
    # отображение, им занимается фронт: бэкенд отдаёт доменные данные, а не
    # готовый текст под UI (то же решение, что по badgeLabel в Этапе 4e).
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    period_year: int
    period_month: int
    status: CampaignStatus
    created_at: datetime


class CampaignListItemOut(BaseModel):
    id: int
    title: str
    period_year: int
    period_month: int
    status: CampaignStatus
    created_at: datetime
    total_assessments: int
    completed_assessments: int


class GenerateIn(BaseModel):
    class_ids: list[int] = Field(min_length=1)
    # Оценивают ли одноклассники друг друга. По умолчанию нет — только
    # самооценка + учителя + родители. True добавляет пиров (student→classmate).
    include_peers: bool = False
    # Какие учителя класса участвуют: {class_id: [teacher_id, ...]}. В школе
    # ученика оценивают не все предметники, а выбранные 2–4 — см.
    # generate_assessments. Класса нет в словаре → берутся ВСЕ учителя класса
    # (прежнее поведение, на нём стоят старые кампании и тесты); класс есть с
    # пустым списком → учительских анкет по нему не будет вовсе.
    teacher_ids_by_class: dict[int, list[int]] | None = None


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
    campaign_title: str
    subject: UserOut
    # Нужна фронту, чтобы решить, показывать ли баннер анонимности (только
    # при PEER) — без похода за списком анкет, где уже есть is_self.
    rater_role: RaterRole
    questions: list[QuestionForAssessmentOut]


class AssessmentListItemOut(BaseModel):
    id: int
    campaign_id: int
    campaign_title: str
    campaign_period_year: int
    campaign_period_month: int
    subject: UserOut
    is_self: bool
    rater_role: RaterRole
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
