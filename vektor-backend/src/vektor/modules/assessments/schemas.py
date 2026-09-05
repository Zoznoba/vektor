# Pydantic-схемы assessments. Вход — что клиент имеет право прислать,
# выход — что мы готовы показать.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class CampaignDeleteResult(BaseModel):
    """Что именно снесли — под подтверждение в UI («удалено N анкет, M ответов»).

    Возвращаем тело, а не 204: удаление кампании необратимо и утаскивает за
    собой чужую работу, поэтому админ должен увидеть масштаб постфактум, а не
    только «ок».
    """

    campaign_id: int
    assessments_deleted: int
    answers_deleted: int


class GenerateIn(BaseModel):
    """Из чего собирается кампания: классы и/или кейсы.

    `class_ids` больше не обязателен: кампанию можно собрать по одним кейсам
    (диагностика кружка) — но и пустым целиком запрос быть не может, иначе
    генерация молча не создаст ни одной анкеты и отчитается «создано 0», что
    для админа неотличимо от «всё уже было сгенерировано».
    """

    class_ids: list[int] = Field(default_factory=list)
    # Оценивают ли одноклассники друг друга. По умолчанию нет — только
    # самооценка + учителя + родители. True добавляет пиров (student→classmate).
    include_peers: bool = False
    # Какие учителя класса участвуют: {class_id: [teacher_id, ...]}. В школе
    # ученика оценивают не все предметники, а выбранные 2–4 — см.
    # generate_assessments. Класса нет в словаре → берутся ВСЕ учителя класса
    # (прежнее поведение, на нём стоят старые кампании и тесты); класс есть с
    # пустым списком → учительских анкет по нему не будет вовсе.
    teacher_ids_by_class: dict[int, list[int]] | None = None
    # Кейсы (профильные группы) — второе основание для выдачи анкет наравне с
    # классами. В кружке ученика оценивают его руководители, а не предметники
    # класса, поэтому свой список учителей: {case_id: [teacher_id, ...]},
    # семантика ключей та же, что у teacher_ids_by_class.
    case_ids: list[int] = Field(default_factory=list)
    teacher_ids_by_case: dict[int, list[int]] | None = None

    @model_validator(mode="after")
    def _at_least_one_source(self) -> "GenerateIn":
        if not self.class_ids and not self.case_ids:
            raise ValueError("Укажите хотя бы один класс или кейс")
        return self


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

    # Критерий и глава («ОР / навык») приходят ВМЕСТЕ с вопросом, а не
    # добираются фронтом из GET /competencies. Тот справочник отдаёт только
    # ДЕЙСТВУЮЩУЮ методику (без is_archived), а уже опубликованная редакция
    # анкеты может содержать вопросы критерия, заархивированного позже —
    # архивирование не переписывает прошлые редакции (7l). На таком вопросе
    # группировка по справочнику молча теряла строку, и анкета не могла
    # завершиться: ответить на «пропавшие» вопросы было негде.
    competency_name: str
    competency_order: int
    outcome_area_id: int
    outcome_area_name: str
    outcome_area_order: int


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
