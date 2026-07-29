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
from vektor.modules.users.models import User
from vektor.shared.enums import CampaignStatus


class CampaignNotFound(Exception):
    """Кампания с таким id не найдена."""


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
) -> set[tuple[int, int]]:
    """Чистое доменное ядро: строит множество пар (respondent_id, subject_id)
    для ОДНОГО класса. Без БД — юнит-тестируется на голых числах (срез 4d).

    Правила (субъект всегда student):
      • самооценка:    (s, s)                 для каждого ученика s
      • одноклассники: (other, s)             для каждого другого ученика класса
      • родители:      (parent, s)            для каждого родителя ученика s
      • учителя:       (teacher, s)           для каждого учителя класса

    Возвращаем set — дубли (напр. родитель, который заодно учитель) схлопнутся
    сами, а вызывающий код объединяет пары нескольких классов через |=.
    """
    pairs: set[tuple[int, int]] = set()
    # TODO: наполни pairs по четырём правилам выше.
    #   Подсказка: самооценка + одноклассники вместе — это просто «каждый ученик
    #   класса оценивает каждого» (включая себя). То есть двойной цикл по
    #   student_ids даёт и (s, s), и (other, s) разом. Родителей и учителей
    #   добавляешь отдельными циклами. parent_ids_by_student.get(s, []) — на
    #   случай ученика без привязанных родителей.
    return pairs


async def generate_assessments(
    db: AsyncSession, campaign_id: int, class_ids: list[int]
) -> tuple[Campaign, int]:
    """Оркестрация: грузит классы из БД, строит матрицу через build_pairs,
    идемпотентно вставляет НОВЫЕ анкеты, переводит кампанию в ACTIVE.
    Возвращает (campaign, сколько_новых_создано)."""

    # TODO 1: достать кампанию. db.get(Campaign, campaign_id); если None → raise CampaignNotFound.

    # TODO 2: загрузить классы со студентами (+ их родителями) и учителями ОДНИМ запросом.
    #   select(SchoolClass).where(SchoolClass.id.in_(class_ids)).options(
    #       selectinload(SchoolClass.students).selectinload(User.parents),
    #       selectinload(SchoolClass.teachers),
    #   )
    #   Иначе доступ к cls.students[i].parents в async-коде даст MissingGreenlet
    #   (ленивая догрузка вне greenlet) — тот самый урок Этапа 3.5.

    # TODO 3: собрать все пары по всем классам.
    #   all_pairs: set[tuple[int, int]] = set()
    #   для каждого cls: вытащить student_ids, parent_ids_by_student
    #   ({s.id: [p.id for p in s.parents] ...}), teacher_ids и
    #   all_pairs |= build_pairs(...).

    # TODO 4: идемпотентность — какие пары уже есть в этой кампании.
    #   select(Assessment.respondent_id, Assessment.subject_id).where(
    #       Assessment.campaign_id == campaign_id)
    #   result.all() вернёт список кортежей (respondent_id, subject_id) —
    #   заверни в set и вычти из all_pairs, чтобы не нарушить UniqueConstraint.

    # TODO 5: db.add_all([Assessment(campaign_id=..., respondent_id=r, subject_id=s)
    #   for r, s in new_pairs]).

    # TODO 6: перевести кампанию в активную: campaign.status = CampaignStatus.ACTIVE.
    #   await db.commit(); await db.refresh(campaign).
    #   Вернуть (campaign, len(new_pairs)).
    ...