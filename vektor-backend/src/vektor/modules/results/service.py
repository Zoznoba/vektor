# Срез 5a — чистые доменные функции агрегации результатов. Без БД,
# юнит-тестируются на синтетических данных (тот же стиль, что build_pairs/
# is_question_visible/compute_status в assessments/service.py).
#
# Дальше (5b) поверх этих функций появится async-код, который тянет Answer
# из БД, классифицирует респондента по роли через реальные отношения
# (subject.school_class.teachers, subject.parents) и вызывает всё это.
#
# ВАЖНО из «Находки из прототипа» (CLAUDE.md): если ответов от одноклассников
# меньше порога — роль PEER не просто занижается, а ИСКЛЮЧАЕТСЯ целиком из
# всех агрегатов (не показывается никому). Это не косметика, а правило,
# которое должно быть видно в тестах на aggregate/overall функциях.

from dataclasses import dataclass

from vektor.shared.enums import RaterRole

DEFAULT_PEER_ANONYMITY_THRESHOLD = 3


@dataclass(frozen=True)
class ScoredAnswer:
    """Один ответ, уже привязанный к компетенции и роли оценивающего — то,
    что 5b насобирает из Answer+Question+respondent для одного (campaign_id,
    subject_id). competency_id — просто int, без relationship."""

    competency_id: int
    rater_role: RaterRole
    value: int


def classify_rater_role(
    respondent_id: int,
    subject_id: int,
    teacher_ids: set[int],
    parent_ids: set[int],
) -> RaterRole:
    """Определить роль респондента относительно субъекта.

    Правила как в build_pairs (assessments/service.py): self проверяем
    первым (совпадение id важнее любой другой связи), дальше teacher/parent,
    всё остальное — одноклассник.
    """
    if respondent_id == subject_id:
        return RaterRole.SELF
    if respondent_id in teacher_ids:
        return RaterRole.TEACHER
    if respondent_id in parent_ids:
        return RaterRole.PARENT
    return RaterRole.PEER


def peers_ok(peer_respondent_count: int, threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD) -> bool:
    """Достаточно ли ответов одноклассников, чтобы не деанонимизировать."""
    return peer_respondent_count >= threshold


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


def overall_by_competency(
    role_scores: dict[int, dict[RaterRole, float]],
    peers_are_ok: bool,
) -> dict[int, float]:
    """«Итоговый» балл по компетенции — среднее по ролям оценивающих.

    SELF участвует наравне с остальными (см. totalAvg() в прототипе — self
    не взвешивается отдельно). Если peers_are_ok=False — роль PEER не
    участвует в среднем, даже если для неё есть значение в role_scores.
    Компетенция без единой роли после фильтрации в результат не попадает.
    """
    result: dict[int, float] = {}
    for competency_id, scores in role_scores.items():
        relevant = {
            role: value for role, value in scores.items() if peers_are_ok or role != RaterRole.PEER
        }
        if relevant:
            result[competency_id] = sum(relevant.values()) / len(relevant)
    return result


def compute_gap(
    self_scores: dict[int, float],
    others_scores: dict[int, float],
) -> dict[int, float]:
    """Разрыв самооценки: self_scores[c] - others_scores[c] по компетенции.

    Компетенция, которой нет в self_scores ИЛИ в others_scores, в результат
    не попадает — не можем посчитать разрыв без обеих сторон.
    """
    return {
        competency_id: self_scores[competency_id] - others_scores[competency_id]
        for competency_id in self_scores
        if competency_id in others_scores
    }


def pick_growth_zones(overall_scores: dict[int, float], n: int = 3) -> list[int]:
    """Top-n компетенций с наименьшим итоговым баллом — «зоны роста».

    Сортировка по (балл, competency_id) — при равных баллах порядок
    детерминирован (меньший id раньше), тесты не будут flaky.
    """
    ordered = sorted(overall_scores.items(), key=lambda item: (item[1], item[0]))
    return [competency_id for competency_id, _ in ordered[:n]]
