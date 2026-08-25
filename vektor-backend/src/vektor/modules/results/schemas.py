# Pydantic-схемы results. Названия полей — *_avg, чтобы не заводить поле с
# именем `self` (в Pydantic v2 формально можно, но повод для путаницы лишний).

from pydantic import BaseModel

from vektor.modules.auth.schemas import UserOut
from vektor.shared.enums import AssessmentStatus, CampaignStatus


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
    period_year: int
    period_month: int
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
    campaign_period_year: int
    campaign_period_month: int

    # None — предыдущего периода нет. Это штатное состояние (первый год
    # ученика), а не ошибка: 404 здесь был бы неверен.
    previous_campaign_id: int | None
    previous_campaign_title: str | None
    previous_campaign_period_year: int | None
    previous_campaign_period_month: int | None

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
    campaign_period_year: int
    campaign_period_month: int

    students_with_results: int
    class_average: float | None
    school_average: float | None

    competencies: list[CompetencyClassScoreOut]
    growth_zones: list[ClassGrowthZoneOut]


class LayerCoverageOut(BaseModel):
    """Один слой раторов про одного ученика: сколько анкет выдано и сколько
    из них завершено.

    Считаем ПАРУ чисел, а не булево «оценили»: родителей у ученика бывает
    двое, учителей в кампании 2–4 (см. 7o), и «1 из 2» — это не то же самое,
    что «готово». `total == 0` означает «слой не выдавали вовсе» — состояние,
    отличное от «выдали, но не заполнили», и на экране это разные значки.
    """

    total: int
    completed: int


class CampaignStudentRowOut(BaseModel):
    """Строка ученика на админском экране кампании: прошла ли самооценка,
    оценили ли родители, оценили ли учителя."""

    subject: UserOut

    # None — самооценки в кампании нет вовсе (анкету не сгенерировали).
    # Отличается от not_started ровно как в ClassRosterRowOut: «не выдана» и
    # «выдана, но не начата» — разные состояния и разные действия админа.
    self_status: AssessmentStatus | None

    parents: LayerCoverageOut
    teachers: LayerCoverageOut
    # Слой одноклассников убран из UI генерации (7o), но данные по нему в
    # прошлых кампаниях есть — отдаём, фронт показывает строку только при
    # total > 0.
    peers: LayerCoverageOut


class ClassCoverageRowOut(BaseModel):
    # None — анкеты без снапшота класса (субъект вне класса, пилот на
    # учителях). Строку не выбрасываем, иначе итог не сойдётся.
    class_id: int | None
    class_label: str | None
    total: int
    completed: int
    percent: float

    # Детализация той же строки по ученикам. Живёт ВНУТРИ покрытия, а не в
    # отдельном эндпоинте: числа шапки («X из Y») и детали обязаны сходиться,
    # а два независимых запроса по одним и тем же анкетам рано или поздно
    # разойдутся — ровно та же причина, по которой агрегаты класса в 5e
    # строятся поверх индивидуальных профилей.
    students: list[CampaignStudentRowOut]


class CampaignCoverageOut(BaseModel):
    campaign_id: int
    campaign_title: str
    campaign_period_year: int
    campaign_period_month: int
    total: int
    completed: int
    percent: float
    classes: list[ClassCoverageRowOut]


# ---------- Состав класса с прогрессом (экран учителя «Мои классы») ----------


class ClassRosterRowOut(BaseModel):
    subject: UserOut

    # None — самооценки в кампании нет вовсе (анкету не сгенерировали).
    # Отличается от not_started: «не выдана» и «выдана, но не начата» — разные
    # состояния, и для учителя разные действия.
    self_status: AssessmentStatus | None
    # «Собрано»: сколько анкет ПРО этого ученика завершено из выданных.
    assessments_total: int
    assessments_completed: int

    overall_avg: float | None
    # Итог прошлого периода и дельта — по ОБЩЕМУ ЯДРУ критериев, как в
    # DynamicsOut.core_average: иначе появление возрастного критерия читалось
    # бы как рост ученика.
    previous_overall_avg: float | None
    delta: float | None
    # Сколько критериев попало в ЛИЧНЫЕ зоны роста ученика — под фильтр «есть
    # зоны роста» на экране учителя. Считаем той же pick_growth_zones, что и
    # везде: порог по среднему баллу дал бы другой список, и фильтр разошёлся
    # бы с тем, что ученик видит у себя в результатах.
    growth_zone_count: int


class ClassRosterOut(BaseModel):
    class_id: int
    class_label: str
    campaign_id: int
    campaign_title: str
    campaign_period_year: int
    campaign_period_month: int

    # Метрики шапки экрана. Считаются здесь, а не на фронте: покрытие берётся
    # по снапшоту subject_class_id, и второе место подсчёта разошлось бы с
    # админским /campaigns/{id}/coverage.
    students_count: int
    assessments_total: int
    assessments_completed: int
    coverage_percent: float
    class_average: float | None
    average_delta: float | None

    students: list[ClassRosterRowOut]
