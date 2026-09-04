# Pydantic-схемы results. Названия полей — *_avg, чтобы не заводить поле с
# именем `self` (в Pydantic v2 формально можно, но повод для путаницы лишний).

from typing import Literal

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


class ClassSchoolGapOut(BaseModel):
    """Критерий, по которому класс отстаёт от школы за тот же период.

    Отвечает на вопрос «чем ЭТОТ класс отличается»: критерий, низкий у всей
    школы, — не проблема класса, и классный час по нему бессмысленен.
    `delta` всегда отрицательная — в список попадают только отстающие.
    """

    competency_id: int
    code: str
    name: str
    delta: float
    class_avg: float | None
    school_avg: float | None


class GroupSelfGapOut(BaseModel):
    """Критерий с наибольшим расхождением «самооценка − окружающие» по группе.

    Единственное место на экране группы, где видно собственно 360°: средний
    балл и сравнение со школой одинаково считались бы и по обычной оценке
    учителя. Знак сохраняется: «себя выше» и «себя ниже» — два разных
    разговора с классом.
    """

    competency_id: int
    code: str
    name: str
    gap: float
    self_avg: float | None
    others_avg: float | None


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
    school_gaps: list[ClassSchoolGapOut]
    self_gaps: list[GroupSelfGapOut]


class CompetencyCaseScoreOut(BaseModel):
    """Критерий в профиле кейса. Поля названы иначе, чем у класса
    (`case_avg` вместо `class_avg`), намеренно: фронт не должен угадывать по
    одинаковому имени, чей это профиль."""

    competency_id: int
    code: str
    name: str
    case_avg: float | None
    school_avg: float | None


class CaseSchoolGapOut(BaseModel):
    """То же, что ClassSchoolGapOut, но для кейса."""

    competency_id: int
    code: str
    name: str
    delta: float
    case_avg: float | None
    school_avg: float | None


class CaseResultsOut(BaseModel):
    case_id: int
    case_name: str
    campaign_id: int
    campaign_title: str
    campaign_period_year: int
    campaign_period_month: int

    students_with_results: int
    case_average: float | None
    school_average: float | None

    competencies: list[CompetencyCaseScoreOut]
    school_gaps: list[CaseSchoolGapOut]
    self_gaps: list[GroupSelfGapOut]


class GroupDynamicsOut(BaseModel):
    """Динамика группы по критериям: текущий период против предыдущего.

    Сравниваются ОДНИ И ТЕ ЖЕ ученики — те, у кого есть оба периода, —
    поэтому `students_compared` может быть меньше состава группы
    (`students_total`): пришедший в этом году новичок сдвигал бы «текущее», и
    разница читалась бы как рост коллектива.

    `class_id`/`class_label` и `case_id`/`case_name` — взаимоисключающие:
    заполнена та пара, чей эндпоинт вызвали. Одна схема на оба, потому что
    остальные два десятка полей совпадают полностью.
    """

    class_id: int | None = None
    class_label: str | None = None
    case_id: int | None = None
    case_name: str | None = None

    campaign_id: int
    campaign_title: str
    campaign_period_year: int
    campaign_period_month: int

    # None — предыдущего периода нет вовсе (пятиклассники). Это штатное
    # состояние, а не ошибка: отдаём текущие баллы без дельт.
    previous_campaign_id: int | None
    previous_campaign_period_year: int | None
    previous_campaign_period_month: int | None

    students_compared: int
    students_total: int

    versions_differ: bool
    version_note: str | None

    core_competencies_count: int
    core_average: float | None
    previous_core_average: float | None
    core_average_delta: float | None

    competencies: list[CompetencyDynamicsOut]


class RaterStatusOut(BaseModel):
    """Один оценивающий внутри слоя: кто и заполнил ли анкету.

    Нужен, чтобы «1 из 2» можно было раскрыть до имени: админу, который
    собирается напомнить, важно не число, а КТО именно не заполнил.
    """

    id: int
    full_name: str
    status: AssessmentStatus


class LayerCoverageOut(BaseModel):
    """Один слой раторов про одного ученика: сколько анкет выдано, сколько
    из них завершено и кто эти люди поимённо.

    Считаем ПАРУ чисел, а не булево «оценили»: родителей у ученика бывает
    двое, учителей в кампании 2–4 (см. 7o), и «1 из 2» — это не то же самое,
    что «готово». `total == 0` означает «слой не выдавали вовсе» — состояние,
    отличное от «выдали, но не заполнили», и на экране это разные значки.

    Поимённый состав отдаём ВМЕСТЕ со счётчиками, а не отдельным эндпоинтом
    «раскрыть слой»: список короткий (двое родителей, 2–4 учителя), а второй
    запрос по тем же анкетам рано или поздно разошёлся бы со счётчиками —
    та же причина, по которой детализация по ученикам живёт внутри покрытия.
    """

    total: int
    completed: int
    raters: list[RaterStatusOut]


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


class CoverageGroupOut(BaseModel):
    """Одна строка покрытия — класс ИЛИ кейс.

    Кампания собирается из двух источников (Этап 8), и группировать всё по
    классу нельзя: анкеты кружка приплюсовывались бы к классам его
    участников, и админ не видел бы, выдана ли диагностика по кейсу вообще.

    Основание выдачи — снапшот на анкете: есть `subject_case_id` → строка
    кейса, иначе строка класса. Именно ИЛИ, а не обе сразу: анкета попадает
    ровно в одну строку, поэтому сумма строк по-прежнему равна общему числу
    анкет кампании.
    """

    # kind различает строки явно: у класса и кейса независимая нумерация, и
    # class_id=3 с case_id=3 — разные сущности с одним числом.
    kind: Literal["class", "case", "none"]

    # None — анкеты без снапшота класса (субъект вне класса, пилот на
    # учителях). Строку не выбрасываем, иначе итог не сойдётся.
    class_id: int | None
    class_label: str | None
    case_id: int | None = None
    case_name: str | None = None
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
    # Именно groups, а не classes: с Этапа 8 в списке живут и кейсы, а
    # название поля, врущее про содержимое, — источник ошибок при чтении кода.
    groups: list[CoverageGroupOut]


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
