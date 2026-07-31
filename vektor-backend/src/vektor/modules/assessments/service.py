# Бизнес-логика assessments. Права (только админ создаёт/генерит кампанию)
# проверяются в роутере через require_role(ADMIN) — здесь не дублируем.
#
# Срез 4b-1: создание кампании.
# Срез 4b-2 (следующий): generate_assessments — матрица «кто кого оценивает».

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.assessments.models import Assessment, Campaign
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Question
from vektor.modules.users.models import User
from vektor.shared.enums import CampaignStatus


class CampaignNotFound(Exception):
    """Кампания с таким id не найдена."""


class AssessmentNotFound(Exception):
    """Анкета с таким id не найдена."""


class NotAssessmentOwner(Exception):
    """Пользователь пытается открыть/заполнить не свою анкету."""


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
    
    subject_grade = None
    if assessment.subject.school_class:
        subject_grade = assessment.subject.school_class.grade
        
    q_ordered_questions = await db.execute(
        select(Question).order_by(Question.competency_id, Question.order)
    )
    ordered_questions=  q_ordered_questions.scalars()
    
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
        for q in ordered_questions
        if is_question_visible(q.is_conditional, subject_grade)
    ]

    return {
        "id": assessment.id,
        "campaign_id": assessment.campaign_id,
        "subject": assessment.subject,
        "questions": questions,
    }
