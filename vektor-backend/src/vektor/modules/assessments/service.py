# Бизнес-логика assessments. Права (только админ создаёт/генерит кампанию)
# проверяются в роутере через require_role(ADMIN) — здесь не дублируем.
#
# Срез 4b-1: создание кампании.
# Срез 4b-2 (следующий): generate_assessments — матрица «кто кого оценивает».

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.assessments.models import Answer, Assessment, Campaign
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Question
from vektor.modules.users.models import User
from vektor.shared.enums import AssessmentStatus, CampaignStatus


class CampaignNotFound(Exception):
    """Кампания с таким id не найдена."""


class AssessmentNotFound(Exception):
    """Анкета с таким id не найдена."""


class NotAssessmentOwner(Exception):
    """Пользователь пытается открыть/заполнить не свою анкету."""


class CampaignNotActive(Exception):
    """Кампания не в статусе active — приём ответов закрыт."""


class QuestionNotAllowed(Exception):
    """Ответ на вопрос, которого нет в видимом наборе этой анкеты."""


async def create_campaign(
    db: AsyncSession,
    title: str,
    period: str,
    opens_at: datetime | None,
    closes_at: datetime | None,
) -> Campaign:

    campaign = Campaign(
        title=title,
        period=period,
        opens_at=opens_at,
        closes_at=closes_at,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


def build_pairs(
    student_ids: list[int],
    parent_ids_by_student: dict[int, list[int]],
    teacher_ids: list[int],
    include_peers: bool = False,
) -> set[tuple[int, int]]:
    """Чистое доменное ядро: строит множество пар (respondent_id, subject_id)
    для ОДНОГО класса. Без БД — юнит-тестируется на голых числах (срез 4d).

    Правила (субъект всегда student):
      • самооценка:    (s, s)                 ВСЕГДА, для каждого ученика s
      • родители:      (parent, s)            для каждого родителя ученика s
      • учителя:       (teacher, s)           для каждого учителя класса
      • одноклассники: (other, s)             ТОЛЬКО если include_peers=True

    Возвращаем set — дубли (напр. родитель, который заодно учитель) схлопнутся
    сами, а вызывающий код объединяет пары нескольких классов через |=.
    """
    pairs: set[tuple[int, int]] = set()

    for s in student_ids:
        pairs.add((s, s))
        for p in parent_ids_by_student.get(s, []):
            pairs.add((p, s))
        for t in teacher_ids:
            pairs.add((t, s))

    if include_peers:
        for i, r in enumerate(student_ids):
            for s in student_ids[i + 1 :]:
                pairs.add((r, s))
                pairs.add((s, r))

    return pairs


async def generate_assessments(
    db: AsyncSession, campaign_id: int, class_ids: list[int], include_peers: bool = False
) -> tuple[Campaign, int]:
    """Оркестрация: грузит классы из БД, строит матрицу через build_pairs,
    идемпотентно вставляет НОВЫЕ анкеты, переводит кампанию в ACTIVE.
    Возвращает (campaign, сколько_новых_создано)."""

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise CampaignNotFound()

    classes_sample = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id.in_(class_ids))
        .options(
            selectinload(SchoolClass.students).selectinload(User.parents),
            selectinload(SchoolClass.teachers),
        )
    )

    all_pairs: set[tuple[int, int]] = set()

    for cls in classes_sample.scalars():
        student_ids = [s.id for s in cls.students]
        parent_ids_by_student = {s.id: [p.id for p in s.parents] for s in cls.students}
        teacher_ids = [t.id for t in cls.teachers]

        all_pairs |= build_pairs(student_ids, parent_ids_by_student, teacher_ids, include_peers)

    existing_pairs = await db.execute(
        select(Assessment.respondent_id, Assessment.subject_id).where(
            Assessment.campaign_id == campaign_id
        )
    )

    new_pairs = all_pairs - set(existing_pairs.all())
    db.add_all(
        [Assessment(campaign_id=campaign_id, respondent_id=r, subject_id=s) for r, s in new_pairs]
    )

    campaign.status = CampaignStatus.ACTIVE
    await db.commit()
    await db.refresh(campaign)

    return campaign, len(new_pairs)


def is_question_visible(is_conditional: bool, subject_grade: int | None) -> bool:
    """Чистое доменное правило: показывать ли вопрос в анкете про субъекта.

    Базовые вопросы (is_conditional=False) — всегда. Условные — только если
    класс субъекта 9–11. Если класс неизвестен (subject_grade=None) — прячем.
    Юнит-тестируется без БД.
    """
    if not is_conditional:
        return True
    return subject_grade is not None and 9 <= subject_grade <= 11


async def get_visible_questions_for_subject(db: AsyncSession, subject: User) -> list[Question]:
    """Все вопросы (упорядоченные по competency_id, order), видимые для анкеты
    про данного субъекта — с учётом его класса (is_question_visible)."""
    subject_grade = subject.school_class.grade if subject.school_class else None

    q_ordered_questions = await db.execute(
        select(Question).order_by(Question.competency_id, Question.order)
    )
    return [
        q
        for q in q_ordered_questions.scalars()
        if is_question_visible(q.is_conditional, subject_grade)
    ]


async def get_assessment_detail(db: AsyncSession, assessment_id: int, current_user_id: int) -> dict:
    """Собрать анкету для прохождения: субъект + видимые вопросы с уже данными
    ответами. Видит только сам респондент (владелец анкеты)."""

    q_assessment = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.answers),
        )
    )
    assessment = q_assessment.scalar_one_or_none()
    if assessment is None:
        raise AssessmentNotFound()

    if assessment.respondent_id != current_user_id:
        raise NotAssessmentOwner()

    visible_questions = await get_visible_questions_for_subject(db, assessment.subject)
    already_answered = {answer.question_id: answer.value for answer in assessment.answers}

    questions = [
        {
            "id": q.id,
            "competency_id": q.competency_id,
            "text": q.text,
            "order": q.order,
            "is_conditional": q.is_conditional,
            "value": already_answered.get(q.id),
        }
        for q in visible_questions
    ]

    return {
        "id": assessment.id,
        "campaign_id": assessment.campaign_id,
        "subject": assessment.subject,
        "questions": questions,
    }


def compute_status(answered_questions: int, total_questions: int) -> AssessmentStatus:
    """Чистое правило статуса анкеты по прогрессу. Юнит-тестируется без БД.

    0 отвеченных → not_started; всё видимое отвечено → completed;
    что-то посередине → in_progress. total_questions=0 (нет видимых вопросов)
    трактуем как completed — заполнять нечего.
    """
    if total_questions == 0 or answered_questions >= total_questions:
        return AssessmentStatus.COMPLETED
    if answered_questions == 0:
        return AssessmentStatus.NOT_STARTED
    return AssessmentStatus.IN_PROGRESS


async def list_my_assessments(
    db: AsyncSession, current_user_id: int, campaign_id: int | None = None
) -> list[dict]:
    """Все анкеты, где current_user — респондент (то, что ему предстоит/уже
    заполнено), опционально отфильтрованные по кампании. Прогресс считается
    так же, как в submit_answers — по видимым для субъекта вопросам."""

    query = (
        select(Assessment)
        .where(Assessment.respondent_id == current_user_id)
        .options(
            selectinload(Assessment.campaign),
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.answers),
        )
    )
    if campaign_id is not None:
        query = query.where(Assessment.campaign_id == campaign_id)

    result = await db.execute(query)

    items = []
    for assessment in result.scalars():
        visible_ids = {q.id for q in await get_visible_questions_for_subject(db, assessment.subject)}
        answered = {a.question_id for a in assessment.answers} & visible_ids
        items.append(
            {
                "id": assessment.id,
                "campaign_id": assessment.campaign_id,
                "campaign_title": assessment.campaign.title,
                "campaign_period": assessment.campaign.period,
                "subject": assessment.subject,
                "is_self": assessment.respondent_id == assessment.subject_id,
                "status": assessment.status,
                "answered_questions": len(answered),
                "total_questions": len(visible_ids),
            }
        )
    return items


async def submit_answers(
    db: AsyncSession, assessment_id: int, current_user_id: int, answers: list
) -> dict:
    """Атомарно сохранить пачку ответов (upsert) и пересчитать статус анкеты.
    answers — list[AnswerIn] (у каждого .question_id и .value).

    Всё в ОДНОЙ транзакции: любая проверка падает ДО commit → ничего не пишется.
    """

    assessment_query = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.campaign),
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.answers),
        )
    )
    assessment = assessment_query.scalar_one_or_none()
    if assessment is None:
        raise AssessmentNotFound()

    if assessment.respondent_id != current_user_id:
        raise NotAssessmentOwner()

    if assessment.campaign.status != CampaignStatus.ACTIVE:
        raise CampaignNotActive()

    visible_questions = await get_visible_questions_for_subject(db, assessment.subject)
    visible_ids = {q.id for q in visible_questions}

    existing_answers = {a.question_id: a for a in assessment.answers}

    # Сначала валидация: все присланные question_id должны быть в видимом наборе
    for incoming_answer in answers:
        if incoming_answer.question_id not in visible_ids:
            raise QuestionNotAllowed()

    # Затем апдейт/инсерт, чтобы не было частичного сохранения (транзакция откатится при ошибке)
    for incoming_answer in answers:
        if incoming_answer.question_id in existing_answers:
            existing_answers[incoming_answer.question_id].value = incoming_answer.value
        else:
            new_answer = Answer(
                assessment_id=assessment_id,
                question_id=incoming_answer.question_id,
                value=incoming_answer.value,
            )
            db.add(new_answer)

    answered_qids = set(existing_answers.keys()) | {i.question_id for i in answers}
    answered_questions_count = len(visible_ids & answered_qids)
    assessment.status = compute_status(answered_questions_count, len(visible_ids))

    await db.commit()
    return {
        "assessment_id": assessment.id,
        "status": assessment.status,
        "answered_questions": answered_questions_count,
        "total_questions": len(visible_ids),
    }
