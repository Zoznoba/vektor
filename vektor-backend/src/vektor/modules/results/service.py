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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.errors import DomainError
from vektor.modules.assessments.models import Answer, Assessment, Campaign
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Competency, Question, QuestionnaireVersion
from vektor.modules.users.models import User
from vektor.shared.enums import AssessmentStatus, RaterRole, UserRole

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


def overall_scores_from_answers(
    answers: list[ScoredAnswer], threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD
) -> dict[int, float]:
    """Ответы → итоговый балл по компетенциям, ОДНОЙ функцией.

    Вся цепочка (подсчёт пиров → агрегация → redact_peer_scores → overall)
    собрана здесь, чтобы у неё было ровно одно место. Динамика по годам и
    агрегаты класса обязаны считать так же, как страница результатов: если
    редактирование применить где-то по-другому, скрытый слой одноклассников
    «протечёт» через сравнение периодов или через средний профиль класса.
    """
    peer_rater_counts = count_peer_raters_by_competency(answers)
    raw_scores = aggregate_by_competency_and_rater(answers)
    role_scores = redact_peer_scores(raw_scores, peer_rater_counts, threshold)
    return overall_by_competency(role_scores)


# ---------- Срез 5d: динамика между периодами (чистые функции) ----------


def shared_competencies(
    current_scores: dict[int, float], previous_scores: dict[int, float]
) -> set[int]:
    """Общее ядро — компетенции, посчитанные в ОБОИХ периодах.

    Состав критериев между годами меняется: «Исследование профессиональных
    возможностей» открывается только с 9 класса. Сравнивать можно лишь то,
    что мерили и там, и там.
    """
    return set(current_scores) & set(previous_scores)


def compute_deltas(
    current_scores: dict[int, float], previous_scores: dict[int, float], core: set[int]
) -> dict[int, float]:
    """Прирост по компетенциям общего ядра: current - previous.

    Только по ядру: у критерия, появившегося в этом году, «прироста» нет —
    показать там разницу с нулём или с самим собой значило бы нарисовать
    достижение, которого не было.
    """
    return {
        competency_id: current_scores[competency_id] - previous_scores[competency_id]
        for competency_id in core
        if competency_id in current_scores and competency_id in previous_scores
    }


def core_average(scores: dict[int, float], core: set[int]) -> float | None:
    """Средний балл ТОЛЬКО по общему ядру.

    Именно этот итог сравнивают между периодами, а не overall_average из
    get_subject_results: тот считается по всем критериям своего периода, и при
    смене их состава сдвинулся бы сам по себе — без всякого роста ученика.
    """
    relevant = [scores[competency_id] for competency_id in core if competency_id in scores]
    return sum(relevant) / len(relevant) if relevant else None


# ---------- Срез 5e: агрегаты класса (чистые функции) ----------


def average_profiles(profiles: list[dict[int, float]]) -> dict[int, float]:
    """Средний профиль по списку индивидуальных профилей.

    Каждый УЧЕНИК весит одинаково, независимо от того, сколько человек его
    оценивало. Иначе ученик, про которого ответили пятеро, перевесил бы того,
    про кого ответил один, и «средний профиль класса» съехал бы в сторону
    самых охваченных.
    """
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for profile in profiles:
        for competency_id, value in profile.items():
            sums[competency_id] = sums.get(competency_id, 0.0) + value
            counts[competency_id] = counts.get(competency_id, 0) + 1
    return {competency_id: sums[competency_id] / counts[competency_id] for competency_id in sums}


def count_growth_zone_hits(growth_zone_lists: list[list[int]]) -> dict[int, int]:
    """У скольких учеников критерий попал в ЛИЧНЫЕ зоны роста."""
    hits: dict[int, int] = {}
    for zones in growth_zone_lists:
        for competency_id in zones:
            hits[competency_id] = hits.get(competency_id, 0) + 1
    return hits


def rank_growth_zones_by_hits(
    hits: dict[int, int], n: int = DEFAULT_GROWTH_ZONES_COUNT
) -> list[int]:
    """Зоны роста класса — по ОХВАТУ, а не по худшему среднему.

    Критерий может быть слабым местом у восьми учеников из двенадцати и при
    этом не иметь худшего среднего по классу. В прототипе подпись прямая:
    «темы для классных часов, а не список слабых учеников» — поэтому считаем,
    у скольких он в личных зонах, а не насколько низко просел средний балл.
    Сортировка по (-охват, competency_id) — детерминированно при равенстве.
    """
    ordered = sorted(hits.items(), key=lambda item: (-item[1], item[0]))
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


def can_view_class_results(
    current_user_id: int,
    current_user_role: UserRole,
    class_teacher_ids: set[int],
) -> bool:
    """Кто видит класс целиком: admin или учитель ЭТОГО класса (классный
    руководитель входит в teachers по построению — см. classes/service.py).

    Родителю и ученику класс не показываем: в прототипе экран «Мой класс» с
    баллами есть только у учителя и админа. Родитель видит своего ребёнка на
    фоне среднего по классу — это другой экран и другие данные.
    """
    return current_user_role == UserRole.ADMIN or current_user_id in class_teacher_ids


# ---------- DB-часть: сбор ответов, права, сборка ответа эндпоинта ----------


class CampaignNotFound(DomainError):
    """Кампания с таким id не найдена."""

    status_code = 404
    code = "campaign_not_found"
    message = "Кампания не найдена"


class SubjectNotFound(DomainError):
    """Пользователь-субъект с таким id не найден."""

    status_code = 404
    code = "subject_not_found"
    message = "Субъект не найден"


class NotAllowedToViewResults(DomainError):
    """Текущий пользователь не имеет права смотреть результаты этого субъекта."""

    status_code = 403
    code = "not_allowed_to_view_results"
    message = "Нет доступа к этим результатам"


class SchoolClassNotFound(DomainError):
    """Класс с таким id не найден."""

    status_code = 404
    code = "class_not_found"
    message = "Класс не найден"


async def _load_subject_for_results(db: AsyncSession, subject_id: int, current_user: User) -> User:
    """Загрузить субъекта и проверить право текущего пользователя на его
    результаты. Общая точка для страницы результатов и динамики: иначе
    динамика могла бы разойтись с ней в правах и показать чужие баллы.

    Права считаются по ТЕКУЩИМ связям (доступ определяется тем, кто учитель и
    родитель сейчас), а роли в агрегации берутся зафиксированные — см.
    _load_scored_answers.
    """
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

    return subject


async def _overall_scores_for(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> dict[int, float]:
    """Итоговые баллы субъекта за кампанию — через ту же цепочку, что и
    страница результатов (включая redact_peer_scores)."""
    answers = await _load_scored_answers(db, subject_id, campaign_id)
    return overall_scores_from_answers(answers)


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

    subject = await _load_subject_for_results(db, subject_id, current_user)

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


# ---------- Срез 5d: динамика между периодами (БД) ----------


async def list_subject_campaigns(
    db: AsyncSession, subject_id: int, current_user: User
) -> list[dict]:
    """Периоды, за которые у субъекта вообще есть результаты — под переключатель
    кампаний на экране результатов. Порядок хронологический по `period`
    (см. latest_campaign_id_for_subject: id ≠ хронология)."""
    await _load_subject_for_results(db, subject_id, current_user)

    rows = await db.execute(
        select(Campaign)
        .join(Assessment, Assessment.campaign_id == Campaign.id)
        .where(Assessment.subject_id == subject_id)
        .distinct()
        .order_by(Campaign.period.desc(), Campaign.id.desc())
    )
    return [
        {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "period": campaign.period,
            "status": campaign.status,
        }
        for campaign in rows.scalars()
    ]


async def previous_campaign_id_for_subject(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> int | None:
    """Предыдущий период субъекта относительно указанной кампании.

    Ищем по `Campaign.period`, а не по id — по той же причине, что и
    latest_campaign_id_for_subject: архив импортируется позже и получает
    больший id, хотя относится к прошлому году.

    Строго МЕНЬШЕ текущего периода: две кампании одного года (например, разные
    классы) предыдущими друг другу не являются, сравнивать их бессмысленно.
    """
    current = await db.get(Campaign, campaign_id)
    if current is None:
        raise CampaignNotFound()

    row = await db.execute(
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(Assessment.subject_id == subject_id, Campaign.period < current.period)
        .order_by(Campaign.period.desc(), Campaign.id.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def get_subject_dynamics(
    db: AsyncSession, subject_id: int, campaign_id: int, current_user: User
) -> dict:
    """Сравнение текущего периода с предыдущим по общему ядру критериев.

    Отсутствие предыдущего периода — НЕ ошибка: у пятиклассников прошлогодних
    данных нет в принципе. Возвращаем текущие баллы и previous_campaign_id=None,
    фронт сам решает, рисовать ли стрелку.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    subject = await _load_subject_for_results(db, subject_id, current_user)

    current_scores = await _overall_scores_for(db, subject_id, campaign_id)

    previous_id = await previous_campaign_id_for_subject(db, subject_id, campaign_id)
    previous_campaign = await db.get(Campaign, previous_id) if previous_id else None
    previous_scores = await _overall_scores_for(db, subject_id, previous_id) if previous_id else {}

    core = shared_competencies(current_scores, previous_scores)
    deltas = compute_deltas(current_scores, previous_scores, core)

    # Редакция анкеты могла смениться между периодами: формулировки части
    # критериев отличаются, поэтому сравнение приблизительное. Текст оговорки
    # лежит в note архивной редакции — придумывать его здесь нельзя.
    versions_differ = bool(
        previous_campaign
        and previous_campaign.questionnaire_version_id != campaign.questionnaire_version_id
    )
    version_note = None
    if versions_differ:
        version_note = await db.scalar(
            select(QuestionnaireVersion.note).where(
                QuestionnaireVersion.id == previous_campaign.questionnaire_version_id
            )
        )

    competencies_result = await db.execute(select(Competency).order_by(Competency.order))
    competencies = competencies_result.scalars().all()

    competencies_out = [
        {
            "competency_id": comp.id,
            "code": comp.code,
            "name": comp.name,
            "overall_avg": current_scores.get(comp.id),
            "previous_avg": previous_scores.get(comp.id),
            "delta": deltas.get(comp.id),
            # Участвует ли критерий в сравнении. False там, где его не было в
            # прошлом периоде (открылся по возрасту) — значение показываем,
            # дельту нет.
            "in_core": comp.id in core,
        }
        for comp in competencies
        if comp.id in current_scores or comp.id in previous_scores
    ]

    current_core_average = core_average(current_scores, core)
    previous_core_average = core_average(previous_scores, core)

    return {
        "subject": subject,
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period": campaign.period,
        "previous_campaign_id": previous_id,
        "previous_campaign_title": previous_campaign.title if previous_campaign else None,
        "previous_campaign_period": previous_campaign.period if previous_campaign else None,
        "versions_differ": versions_differ,
        "version_note": version_note,
        # Итог по общему ядру, а НЕ overall_average из get_subject_results.
        "core_competencies_count": len(core),
        "core_average": current_core_average,
        "previous_core_average": previous_core_average,
        "core_average_delta": (
            current_core_average - previous_core_average
            if current_core_average is not None and previous_core_average is not None
            else None
        ),
        "competencies": competencies_out,
    }


# ---------- Срез 5e: агрегаты класса и покрытие кампании (БД) ----------


async def latest_campaign_id_for_class(db: AsyncSession, class_id: int) -> int | None:
    """Самая свежая кампания, где у класса есть анкеты (по снапшоту класса).
    Сортировка по `period` — та же причина, что у одноимённой функции для
    субъекта: id не отражает хронологию."""
    row = await db.execute(
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(Assessment.subject_class_id == class_id)
        .order_by(Campaign.period.desc(), Campaign.id.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _subject_class_map(db: AsyncSession, campaign_id: int) -> dict[int, int | None]:
    """subject_id → класс НА МОМЕНТ генерации (снапшот Assessment.
    subject_class_id). Не текущий класс ученика: иначе перевод в следующий
    класс перетаскивал бы прошлогодние результаты в новый."""
    rows = await db.execute(
        select(Assessment.subject_id, Assessment.subject_class_id)
        .where(Assessment.campaign_id == campaign_id)
        .distinct()
    )
    return {subject_id: class_id for subject_id, class_id in rows.all()}


async def _profiles_by_campaign_and_subject(
    db: AsyncSession, campaign_ids: set[int]
) -> dict[tuple[int, int], dict[int, float]]:
    """Индивидуальные профили пачкой: один запрос на все нужные кампании,
    дальше группировка в памяти. Ключ — (campaign_id, subject_id).

    Считаем ПОВЕРХ индивидуальных профилей (overall_scores_from_answers), а не
    отдельным запросом по сырым ответам: иначе правило анонимности пришлось бы
    применять второй раз, в другом месте и по другой формуле — такие дубли
    неизбежно расходятся.
    """
    if not campaign_ids:
        return {}

    rows = await db.execute(
        select(
            Assessment.campaign_id,
            Assessment.subject_id,
            Answer.value,
            Assessment.respondent_id,
            Assessment.rater_role,
            Question.competency_id,
        )
        .join(Assessment, Answer.assessment_id == Assessment.id)
        .join(Question, Answer.question_id == Question.id)
        .where(Assessment.campaign_id.in_(campaign_ids))
    )

    grouped: dict[tuple[int, int], list[ScoredAnswer]] = {}
    for campaign_id, subject_id, value, respondent_id, rater_role, competency_id in rows.all():
        grouped.setdefault((campaign_id, subject_id), []).append(
            ScoredAnswer(
                competency_id=competency_id,
                rater_role=rater_role,
                respondent_id=respondent_id,
                value=value,
            )
        )

    return {key: overall_scores_from_answers(answers) for key, answers in grouped.items()}


async def get_class_results(
    db: AsyncSession, class_id: int, campaign_id: int, current_user: User
) -> dict:
    """Средний профиль класса, сравнение со школой и зоны роста класса."""
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    class_query = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id == class_id)
        .options(selectinload(SchoolClass.teachers))
    )
    school_class = class_query.scalar_one_or_none()
    if school_class is None:
        raise SchoolClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_class_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    class_map = await _subject_class_map(db, campaign_id)
    class_subject_ids = {sid for sid, cid in class_map.items() if cid == class_id}

    # «Школа» — это весь ПЕРИОД, а не одна кампания. В боевых данных кампанию
    # заводят на каждый класс отдельно, поэтому внутри одной кампании «школа»
    # выродилась бы в этот же класс, и сравнение всегда давало бы ноль.
    same_period_campaigns = await db.execute(
        select(Campaign.id).where(Campaign.period == campaign.period)
    )
    campaign_ids = set(same_period_campaigns.scalars())

    all_profiles = await _profiles_by_campaign_and_subject(db, campaign_ids)
    class_profiles = [
        profile
        for (cid, sid), profile in all_profiles.items()
        if cid == campaign_id and sid in class_subject_ids and profile
    ]
    school_profiles = [profile for profile in all_profiles.values() if profile]

    class_scores = average_profiles(class_profiles)
    school_scores = average_profiles(school_profiles)

    # Зоны роста класса — по охвату личных зон, а не по худшему среднему.
    hits = count_growth_zone_hits([pick_growth_zones(profile) for profile in class_profiles])
    zone_ids = rank_growth_zones_by_hits(hits)

    competencies_result = await db.execute(select(Competency).order_by(Competency.order))
    competencies = competencies_result.scalars().all()
    competencies_by_id = {c.id: c for c in competencies}

    return {
        "class_id": class_id,
        "class_label": f"{school_class.grade}-{school_class.section}",
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period": campaign.period,
        "students_with_results": len(class_profiles),
        "class_average": (sum(class_scores.values()) / len(class_scores) if class_scores else None),
        "school_average": (
            sum(school_scores.values()) / len(school_scores) if school_scores else None
        ),
        "competencies": [
            {
                "competency_id": comp.id,
                "code": comp.code,
                "name": comp.name,
                "class_avg": class_scores.get(comp.id),
                "school_avg": school_scores.get(comp.id),
            }
            for comp in competencies
            if comp.id in class_scores or comp.id in school_scores
        ],
        "growth_zones": [
            {
                "competency_id": competency_id,
                "code": competencies_by_id[competency_id].code,
                "name": competencies_by_id[competency_id].name,
                "students_affected": hits[competency_id],
                "class_avg": class_scores.get(competency_id),
            }
            for competency_id in zone_ids
        ],
    }


async def get_campaign_coverage(db: AsyncSession, campaign_id: int) -> dict:
    """«X из Y анкет» по классам — под админский экран кампании.

    Группируем по снапшоту subject_class_id. Анкеты без снапшота (субъект вне
    класса, пилотная кампания на учителях) попадают в отдельную строку с
    class_id=None, а не выбрасываются: иначе итог по классам не сходился бы с
    общим числом анкет.
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    completed = func.count().filter(Assessment.status == AssessmentStatus.COMPLETED)
    rows = await db.execute(
        select(
            Assessment.subject_class_id,
            func.count().label("total"),
            completed.label("completed"),
            SchoolClass.grade,
            SchoolClass.section,
        )
        .outerjoin(SchoolClass, SchoolClass.id == Assessment.subject_class_id)
        .where(Assessment.campaign_id == campaign_id)
        .group_by(Assessment.subject_class_id, SchoolClass.grade, SchoolClass.section)
        # NULLS LAST: строка «без класса» уходит в конец списка, а не в начало.
        .order_by(SchoolClass.grade.asc().nulls_last(), SchoolClass.section.asc().nulls_last())
    )

    classes_out = []
    total_all = 0
    completed_all = 0
    for class_id, total, done, grade, section in rows.all():
        total_all += total
        completed_all += done
        classes_out.append(
            {
                "class_id": class_id,
                "class_label": f"{grade}-{section}" if class_id is not None else None,
                "total": total,
                "completed": done,
                "percent": round(done / total * 100, 1) if total else 0.0,
            }
        )

    return {
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period": campaign.period,
        "total": total_all,
        "completed": completed_all,
        "percent": round(completed_all / total_all * 100, 1) if total_all else 0.0,
        "classes": classes_out,
    }
