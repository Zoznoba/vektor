# Этап 5 — агрегация результатов.
#
# Верх файла — чистые доменные функции (без БД, юнит-тестируются на
# синтетике, тот же стиль, что build_pairs/is_question_visible/compute_status
# в assessments/service.py). Низ — async-часть, которая тянет ответы из БД.
#
# ГЛАВНОЕ ПРАВИЛО (из «Находок из прототипа», CLAUDE.md): если по компетенции
# ответило меньше порога одноклассников — слой PEER по ЭТОЙ компетенции не
# просто занижается, а исчезает целиком: не показывается никому (ни ученику,
# ни учителю, ни родителю) и не участвует ни в одном агрегате.
#
# Порог считается ПО КАЖДОЙ КОМПЕТЕНЦИИ, а не глобально «ответил хоть
# что-нибудь». Анкеты заполняются частями (статус in_progress — штатный),
# поэтому при глобальном подсчёте хватило бы трёх пиров, ответивших на
# РАЗНЫЕ вопросы, чтобы показать компетенцию с единственным ответом — и
# автор вычислялся бы однозначно.
#
# Единая точка применения правила — redact_peer_scores. Всё, что считается
# дальше (overall, зоны роста, разрыв самооценки), работает с уже
# отредактированными данными и поэтому не может случайно «протечь».

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.assessments.models import Answer, Assessment, Campaign
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Competency, Question
from vektor.modules.users.models import User
from vektor.shared.enums import RaterRole, UserRole

DEFAULT_PEER_ANONYMITY_THRESHOLD = 3
DEFAULT_GROWTH_ZONES_COUNT = 3


@dataclass(frozen=True)
class ScoredAnswer:
    """Один ответ, привязанный к компетенции и роли оценивающего.

    respondent_id нужен именно для подсчёта РАЗНЫХ одноклассников: порог
    анонимности — про число людей, а не число ответов (иначе один человек
    «набрал» бы порог сам, ответив на несколько вопросов компетенции).
    """

    competency_id: int
    rater_role: RaterRole
    respondent_id: int
    value: int


def can_disclose_peer_scores(
    peer_rater_count: int, threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD
) -> bool:
    """Можно ли показать балл одноклассников, не выдав автора.

    peer_rater_count — число РАЗНЫХ одноклассников, ответивших по конкретной
    компетенции. Меньше порога — показывать нельзя никому.
    """
    return peer_rater_count >= threshold


def count_peer_raters_by_competency(answers: list[ScoredAnswer]) -> dict[int, int]:
    """Сколько РАЗНЫХ одноклассников ответило по каждой компетенции."""
    peers_by_competency: dict[int, set[int]] = {}
    for answer in answers:
        if answer.rater_role == RaterRole.PEER:
            peers_by_competency.setdefault(answer.competency_id, set()).add(answer.respondent_id)
    return {
        competency_id: len(respondents)
        for competency_id, respondents in peers_by_competency.items()
    }


def aggregate_by_competency_and_rater(
    answers: list[ScoredAnswer],
) -> dict[int, dict[RaterRole, float]]:
    """Сгруппировать answers по (competency_id, rater_role) и усреднить value."""
    grouped: dict[int, dict[RaterRole, list[int]]] = {}
    for answer in answers:
        by_role = grouped.setdefault(answer.competency_id, {})
        by_role.setdefault(answer.rater_role, []).append(answer.value)

    return {
        competency_id: {role: sum(values) / len(values) for role, values in by_role.items()}
        for competency_id, by_role in grouped.items()
    }


def redact_peer_scores(
    role_scores: dict[int, dict[RaterRole, float]],
    peer_rater_counts: dict[int, int],
    threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD,
) -> dict[int, dict[RaterRole, float]]:
    """Вырезать балл одноклассников там, где его показ выдал бы автора.

    ЕДИНСТВЕННОЕ место, где применяется правило анонимности. Всё, что
    считается после (overall, зоны роста, разрыв), получает уже безопасные
    данные — поэтому не может показать то, что показывать нельзя.
    Компетенция, у которой после вырезания не осталось ни одной роли,
    выпадает целиком.
    """
    redacted: dict[int, dict[RaterRole, float]] = {}
    for competency_id, scores in role_scores.items():
        safe = {
            role: value
            for role, value in scores.items()
            if role != RaterRole.PEER
            or can_disclose_peer_scores(peer_rater_counts.get(competency_id, 0), threshold)
        }
        if safe:
            redacted[competency_id] = safe
    return redacted


def overall_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """«Итоговый» балл по компетенции — среднее по ролям оценивающих.

    SELF участвует наравне с остальными (см. totalAvg() в прототипе — self
    не взвешивается отдельно). Ожидает УЖЕ отредактированные role_scores:
    фильтрацией PEER занимается redact_peer_scores, а не эта функция.
    """
    return {
        competency_id: sum(scores.values()) / len(scores)
        for competency_id, scores in role_scores.items()
        if scores
    }


def self_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """Самооценка по компетенции — первая половина «разрыва самооценки»."""
    return {
        competency_id: scores[RaterRole.SELF]
        for competency_id, scores in role_scores.items()
        if RaterRole.SELF in scores
    }


def others_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """Средняя оценка ДРУГИХ (все роли, кроме SELF) по компетенции.

    Вторая половина «разрыва самооценки»: сравнивать самооценку нужно не с
    итогом (в него self входит сам, и разрыв размывается), а именно с
    окружающими. Компетенция, где ответил только сам субъект, выпадает.
    """
    result: dict[int, float] = {}
    for competency_id, scores in role_scores.items():
        others = {role: value for role, value in scores.items() if role != RaterRole.SELF}
        if others:
            result[competency_id] = sum(others.values()) / len(others)
    return result


def compute_gap(
    self_scores: dict[int, float],
    others_scores: dict[int, float],
) -> dict[int, float]:
    """Разрыв самооценки: self_scores[c] - others_scores[c] по компетенции.

    Положительный — субъект оценивает себя выше окружающих, отрицательный —
    ниже. Компетенция, которой нет в self_scores ИЛИ в others_scores, в
    результат не попадает: без обеих сторон разрыв не определён.
    """
    return {
        competency_id: self_scores[competency_id] - others_scores[competency_id]
        for competency_id in self_scores
        if competency_id in others_scores
    }


def pick_growth_zones(
    overall_scores: dict[int, float], n: int = DEFAULT_GROWTH_ZONES_COUNT
) -> list[int]:
    """Top-n компетенций с наименьшим итоговым баллом — «зоны роста».

    Сортировка по (балл, competency_id) — при равных баллах порядок
    детерминирован (меньший id раньше), тесты не будут flaky.
    """
    ordered = sorted(overall_scores.items(), key=lambda item: (item[1], item[0]))
    return [competency_id for competency_id, _ in ordered[:n]]


def can_view_results(
    current_user_id: int,
    current_user_role: UserRole,
    subject_id: int,
    teacher_ids: set[int],
    parent_ids: set[int],
) -> bool:
    """Кто может смотреть результаты субъекта: он сам, admin, учитель его
    класса (teacher_ids) или его родитель (parent_ids). Чистая функция —
    teacher_ids/parent_ids уже посчитаны вызывающим кодом из БД."""
    return (
        current_user_id == subject_id
        or current_user_role == UserRole.ADMIN
        or current_user_id in teacher_ids
        or current_user_id in parent_ids
    )


# ---------- DB-часть: сбор ответов, права, сборка ответа эндпоинта ----------


class CampaignNotFound(Exception):
    """Кампания с таким id не найдена."""


class SubjectNotFound(Exception):
    """Пользователь-субъект с таким id не найден."""


class NotAllowedToViewResults(Exception):
    """Текущий пользователь не имеет права смотреть результаты этого субъекта."""


async def _load_scored_answers(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> list[ScoredAnswer]:
    """Ответы про субъекта в рамках кампании, уже с ролью оценивающего.

    Роль берётся из Assessment.rater_role — зафиксированной при генерации, а
    не выводится из текущего состава класса. Поэтому перевод ученика в другой
    класс не переписывает прошлые результаты задним числом.
    """
    rows = await db.execute(
        select(
            Answer.value,
            Assessment.respondent_id,
            Assessment.rater_role,
            Question.competency_id,
        )
        .join(Assessment, Answer.assessment_id == Assessment.id)
        .join(Question, Answer.question_id == Question.id)
        .where(Assessment.subject_id == subject_id, Assessment.campaign_id == campaign_id)
    )
    return [
        ScoredAnswer(
            competency_id=competency_id,
            rater_role=rater_role,
            respondent_id=respondent_id,
            value=value,
        )
        for value, respondent_id, rater_role, competency_id in rows.all()
    ]


async def latest_campaign_id_for_subject(db: AsyncSession, subject_id: int) -> int | None:
    """Самая свежая кампания, в которой у субъекта есть анкеты. None — их нет.

    Нужна дашборду: он показывает «мои результаты», не зная про кампании.

    Сортируем по `period`, а НЕ по id: порядок создания кампаний не равен
    хронологии. Архив прошлого года импортируется после текущего, получает
    больший id — и «последняя по id» кампания оказывается прошлогодней.
    Ровно это и произошло при первом импорте.
    """
    row = await db.execute(
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(Assessment.subject_id == subject_id)
        .order_by(Campaign.period.desc(), Campaign.id.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def get_subject_results(
    db: AsyncSession,
    subject_id: int,
    campaign_id: int,
    current_user: User,
) -> dict:
    """Собрать результаты субъекта по компетенциям для одной кампании.

    Права: сам субъект, admin, учитель класса субъекта, родитель субъекта —
    иначе NotAllowedToViewResults. Права считаются по ТЕКУЩИМ связям (это
    верно: доступ определяется тем, кто учитель/родитель сейчас), а роли в
    агрегации берутся зафиксированные — см. _load_scored_answers.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    subject_query = await db.execute(
        select(User)
        .where(User.id == subject_id)
        .options(
            selectinload(User.school_class).selectinload(SchoolClass.teachers),
            selectinload(User.parents),
        )
    )
    subject = subject_query.scalar_one_or_none()
    if subject is None:
        raise SubjectNotFound()

    teacher_ids = {t.id for t in subject.school_class.teachers} if subject.school_class else set()
    parent_ids = {p.id for p in subject.parents}

    if not can_view_results(
        current_user.id, current_user.role, subject_id, teacher_ids, parent_ids
    ):
        raise NotAllowedToViewResults()

    scored_answers = await _load_scored_answers(db, subject_id, campaign_id)

    peer_rater_counts = count_peer_raters_by_competency(scored_answers)
    raw_scores = aggregate_by_competency_and_rater(scored_answers)
    # С этой строки и ниже работаем ТОЛЬКО с безопасными данными.
    role_scores = redact_peer_scores(raw_scores, peer_rater_counts)

    overall_scores = overall_by_competency(role_scores)
    self_scores = self_by_competency(role_scores)
    others_scores = others_by_competency(role_scores)
    gaps = compute_gap(self_scores, others_scores)
    growth_zone_ids = pick_growth_zones(overall_scores)

    competencies_result = await db.execute(select(Competency).order_by(Competency.order))
    competencies = competencies_result.scalars().all()
    competencies_by_id = {c.id: c for c in competencies}

    competencies_out = [
        {
            "competency_id": comp.id,
            "code": comp.code,
            "name": comp.name,
            "self_avg": role_scores.get(comp.id, {}).get(RaterRole.SELF),
            "peer_avg": role_scores.get(comp.id, {}).get(RaterRole.PEER),
            "teacher_avg": role_scores.get(comp.id, {}).get(RaterRole.TEACHER),
            "parent_avg": role_scores.get(comp.id, {}).get(RaterRole.PARENT),
            "others_avg": others_scores.get(comp.id),
            "overall_avg": overall_scores.get(comp.id),
            "gap": gaps.get(comp.id),
            "peer_rater_count": peer_rater_counts.get(comp.id, 0),
            "peer_scores_disclosed": RaterRole.PEER in role_scores.get(comp.id, {}),
        }
        for comp in competencies
    ]

    growth_zones_out = [
        {
            "competency_id": competency_id,
            "code": competencies_by_id[competency_id].code,
            "name": competencies_by_id[competency_id].name,
            "overall_avg": overall_scores[competency_id],
        }
        for competency_id in growth_zone_ids
    ]

    overall_average = sum(overall_scores.values()) / len(overall_scores) if overall_scores else None

    return {
        "subject": subject,
        "campaign_id": campaign_id,
        # Слой одноклассников как целое — под баннер «данных недостаточно».
        "any_peer_scores_disclosed": any(
            RaterRole.PEER in scores for scores in role_scores.values()
        ),
        "overall_average": overall_average,
        "competencies": competencies_out,
        "growth_zones": growth_zones_out,
    }
