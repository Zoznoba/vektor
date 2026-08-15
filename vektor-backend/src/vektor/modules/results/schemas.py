# Pydantic-схемы results. Названия полей — *_avg, чтобы не заводить поле с
# именем `self` (в Pydantic v2 формально можно, но повод для путаницы лишний).

from pydantic import BaseModel

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import CampaignStatus


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


# ---------- 5d: динамика ----------


class SubjectCampaignOut(BaseModel):
    campaign_id: int
    title: str
    period: str
    status: CampaignStatus


class CompetencyDynamicsOut(BaseModel):
    competency_id: int
    code: str
    name: str

    overall_avg: float | None
    previous_avg: float | None
    # Только для критериев общего ядра. None у тех, что открылись по возрасту:
    # показывать им «прирост» значило бы нарисовать несуществующее достижение.
    delta: float | None
    in_core: bool


class DynamicsOut(BaseModel):
    subject: UserOut
    campaign_id: int
    campaign_title: str
    campaign_period: str

    # None — предыдущего периода нет. Это штатное состояние (первый год
    # ученика), а не ошибка: 404 здесь был бы неверен.
    previous_campaign_id: int | None
    previous_campaign_title: str | None
    previous_campaign_period: str | None

    # Редакция анкеты сменилась между периодами → сравнение приблизительное.
    versions_differ: bool
    version_note: str | None

    # Итог по ОБЩЕМУ ЯДРУ критериев (не overall_average из /results/{id}):
    # только так сравнение не сдвигается от смены состава критериев.
    core_competencies_count: int
    core_average: float | None
    previous_core_average: float | None
    core_average_delta: float | None

    competencies: list[CompetencyDynamicsOut]


# ---------- 5e: агрегаты класса и покрытие ----------


class CompetencyClassScoreOut(BaseModel):
    competency_id: int
    code: str
    name: str
    class_avg: float | None
    school_avg: float | None


class ClassGrowthZoneOut(BaseModel):
    competency_id: int
    code: str
    name: str
    # У скольких учеников критерий попал в ЛИЧНЫЕ зоны роста — ранжирование
    # идёт по охвату, а не по худшему среднему.
    students_affected: int
    class_avg: float | None


class ClassResultsOut(BaseModel):
    class_id: int
    class_label: str
    campaign_id: int
    campaign_title: str
    campaign_period: str

    students_with_results: int
    class_average: float | None
    school_average: float | None

    competencies: list[CompetencyClassScoreOut]
    growth_zones: list[ClassGrowthZoneOut]


class ClassCoverageRowOut(BaseModel):
    # None — анкеты без снапшота класса (субъект вне класса, пилот на
    # учителях). Строку не выбрасываем, иначе итог не сойдётся.
    class_id: int | None
    class_label: str | None
    total: int
    completed: int
    percent: float


class CampaignCoverageOut(BaseModel):
    campaign_id: int
    campaign_title: str
    campaign_period: str
    total: int
    completed: int
    percent: float
    classes: list[ClassCoverageRowOut]
