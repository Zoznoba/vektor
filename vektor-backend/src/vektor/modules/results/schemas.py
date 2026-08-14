# Pydantic-схемы results. Названия полей — *_avg, чтобы не заводить поле с
# именем `self` (в Pydantic v2 формально можно, но повод для путаницы лишний).

from pydantic import BaseModel

from vektor.modules.auth.schemas import UserOut


class CompetencyScoreOut(BaseModel):
    competency_id: int
    code: str
    name: str

    self_avg: float | None
    # None, если по этой компетенции ответило меньше порога одноклассников —
    # балл скрыт от всех, включая учителя и родителя (см. redact_peer_scores).
    peer_avg: float | None
    teacher_avg: float | None
    parent_avg: float | None

    # Среднее по всем ролям, кроме самооценки — вторая сторона разрыва.
    others_avg: float | None
    overall_avg: float | None
    # self_avg - others_avg. Положительный → себя оценивает выше окружающих.
    gap: float | None

    peer_rater_count: int
    peer_scores_disclosed: bool


class GrowthZoneOut(BaseModel):
    competency_id: int
    code: str
    name: str
    overall_avg: float


class ResultsOut(BaseModel):
    subject: UserOut
    campaign_id: int
    # Уцелел ли слой одноклассников хоть где-то — под баннер «данных
    # недостаточно». Точное решение всегда per-competency.
    any_peer_scores_disclosed: bool
    overall_average: float | None
    competencies: list[CompetencyScoreOut]
    growth_zones: list[GrowthZoneOut]
