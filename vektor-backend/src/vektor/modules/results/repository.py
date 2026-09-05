"""Запросы к БД для результатов.

Тот самый «точечный репозиторий» из CLAUDE.md: полноценный слой заводим
там, где запросы сложные, а агрегация результатов — ровно этот случай.
Здесь только доступ к данным и раскладка строк в словари; права и сборка
ответа эндпоинта — в service.py, доменные правила — в domain.py.
"""

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased, selectinload

from vektor.modules.assessments.errors import CampaignNotFound
from vektor.modules.assessments.models import Answer, Assessment, Campaign
from vektor.modules.cases.models import Case
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Competency, Question, QuestionnaireVersion
from vektor.modules.results.domain import (
    CoverageKey,
    ScoredAnswer,
    SubjectProfile,
    coverage_key,
    overall_scores_from_answers,
    profile_from_answers,
)
from vektor.modules.results.errors import CampaignNotCompleted
from vektor.modules.users.models import User
from vektor.shared.enums import AssessmentStatus, CampaignStatus, RaterRole


async def load_completed_campaign(db: AsyncSession, campaign_id: int) -> Campaign:
    """Кампания для СТРАНИЦЫ РЕЗУЛЬТАТОВ: только завершённая (closed).

    Пока кампания в draft/active, ответы ещё собираются: часть анкет пуста,
    часть заполнена наполовину, и любой агрегат по ним — не «промежуточный
    результат», а случайное число, которое завтра изменится. Особенно это
    видно на порогах: критерий с двумя пришедшими ответами уезжает в зоны
    роста, а слой одноклассников то раскрывается, то снова прячется по мере
    заполнения (см. can_disclose_peer_scores).

    Черновик отсекается тем же правилом заодно — это и чинит артефакт из
    находки 7g в CLAUDE.md: пустая кампания-заглушка больше не может стать
    «последней» и подменить собой реальные результаты.

    Мониторинг хода кампании (покрытие, состав класса с прогрессом) под это
    правило НЕ подпадает — там смысл экрана именно в незавершённой кампании,
    см. latest_campaign_id_for_class(only_completed=False).
    """
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()
    if campaign.status != CampaignStatus.CLOSED:
        raise CampaignNotCompleted()
    return campaign


async def overall_scores_for(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> dict[int, float]:
    """Итоговые баллы субъекта за кампанию — через ту же цепочку, что и
    страница результатов (включая redact_peer_scores)."""
    answers = await load_scored_answers(db, subject_id, campaign_id)
    return overall_scores_from_answers(answers)


async def load_scored_answers(
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

    Сортируем по периоду, а НЕ по id: порядок создания кампаний не равен
    хронологии. Архив прошлого года импортируется после текущего, получает
    больший id — и «последняя по id» кампания оказывается прошлогодней.
    Ровно это и произошло при первом импорте.

    Считаем только ЗАВЕРШЁННЫЕ кампании (см. load_completed_campaign):
    незакрытая кампания не должна подменять собой прошлые результаты, пока
    ответы по ней ещё собираются.
    """
    row = await db.execute(
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(Assessment.subject_id == subject_id)
        .where(Campaign.status == CampaignStatus.CLOSED)
        .order_by(
            Campaign.period_year.desc(),
            Campaign.period_month.desc(),
            Assessment.campaign_id.desc(),
        )
        .limit(1)
    )
    return row.scalar_one_or_none()


async def previous_campaign_id_for_subject(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> int | None:
    """Предыдущий период субъекта относительно указанной кампании.

    Ищем по периоду, а не по id — по той же причине, что и
    latest_campaign_id_for_subject: архив импортируется позже и получает
    больший id, хотя относится к прошлому году.

    Строго МЕНЬШЕ текущего периода: две кампании одного периода (например,
    разные классы) предыдущими друг другу не являются, сравнивать их
    бессмысленно.
    """
    current = await db.get(Campaign, campaign_id)
    if current is None:
        raise CampaignNotFound()

    row = await db.execute(
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(
            Assessment.subject_id == subject_id,
            Campaign.status == CampaignStatus.CLOSED,
            # Кортежное сравнение (год, месяц) — ровно «строго раньше» в одном
            # выражении, без разбора ярлыка в Python, как было до e7b3f9c2a815.
            tuple_(Campaign.period_year, Campaign.period_month)
            < tuple_(current.period_year, current.period_month),
        )
        .order_by(
            Campaign.period_year.desc(),
            Campaign.period_month.desc(),
            Assessment.campaign_id.desc(),
        )
        .limit(1)
    )
    return row.scalar_one_or_none()


async def subject_group_map(
    db: AsyncSession, campaign_id: int, snapshot_column: InstrumentedAttribute
) -> dict[int, int | None]:
    """subject_id → класс ИЛИ кейс НА МОМЕНТ генерации (снапшот
    Assessment.subject_class_id / subject_case_id — колонка приходит
    параметром, отличается только она).

    Именно снапшот, а не текущая привязка ученика: перевод в следующий класс
    и смена кружка — штатные события, и по текущему значению они
    перетаскивали бы прошлогодние результаты в новую группу.
    """
    rows = await db.execute(
        select(Assessment.subject_id, snapshot_column)
        .where(Assessment.campaign_id == campaign_id)
        .distinct()
    )
    return {subject_id: group_id for subject_id, group_id in rows.all()}


async def profiles_by_campaign_and_subject(
    db: AsyncSession, campaign_ids: set[int]
) -> dict[tuple[int, int], SubjectProfile]:
    """Индивидуальные профили пачкой: один запрос на все нужные кампании,
    дальше группировка в памяти. Ключ — (campaign_id, subject_id).

    Считаем ПОВЕРХ индивидуальных профилей (profile_from_answers), а не
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

    return {key: profile_from_answers(answers) for key, answers in grouped.items()}


async def campaign_students_by_group(
    db: AsyncSession, campaign_id: int
) -> dict[CoverageKey, list[dict]]:
    """Ключ группы (класс/кейс, см. coverage_key) → список строк учеников под
    CampaignStudentRowOut.

    Зачем отдельной функцией: get_campaign_coverage уже считает агрегат
    группировкой в SQL, а здесь нужен разрез по РАТОРАМ внутри каждого
    ученика. Это разные измерения одних и тех же анкет; смешивать их в один
    запрос — получить строки вида (класс × ученик × роль) и всё равно
    собирать словарь в Python.

    ВАЖНО — слой берём из Assessment.rater_role, зафиксированной при
    генерации (миграция a1c4e77b93f2), а НЕ из текущих связей класса и
    родительства. Иначе перевод ученика в следующий класс — штатное
    ежегодное событие — переписывал бы прошлую картину: учитель прошлого
    года стал бы «одноклассником» и уехал из слоя teachers в peers. Та же
    причина подробно расписана в CLAUDE.md, Этап 5.

    Самооценку, наоборот, определяем сравнением respondent_id == subject_id,
    а не ролью SELF: так делает assessment_progress_by_subject, и в архивных
    анкетах это работает даже там, где rater_role проставлена backfill'ом.
    Своя анкета в слои не попадает вовсе — иначе ученик считался бы сам себе
    ратором и «2 из 2 учителей» превращалось бы в «3 из 3».

    Учеников, которые числятся в классе СЕЙЧАС, но анкет в кампании не
    получили, здесь НЕТ — в отличие от get_class_roster. Там экран
    мониторинга, и «диагностику не выдали» — главное, что учитель должен
    увидеть. Здесь же таблица детализирует покрытие, посчитанное строго по
    анкетам: строка «0 из 0» не соответствовала бы ни одной цифре выше.
    """
    # Респондента подтягиваем вторым join'ом к тем же users: слой
    # раскрывается до имён («кто из двух родителей не заполнил»), а не только
    # до счётчика. Два join'а к одной таблице — та же история, что и у двух
    # FK на Assessment, поэтому алиас обязателен.
    respondent = aliased(User)
    rows = await db.execute(
        select(
            Assessment.subject_class_id,
            Assessment.subject_case_id,
            Assessment.subject_id,
            Assessment.respondent_id,
            Assessment.rater_role,
            Assessment.status,
            User,
            respondent.full_name,
        )
        .join(User, User.id == Assessment.subject_id)
        .join(respondent, respondent.id == Assessment.respondent_id)
        .where(Assessment.campaign_id == campaign_id)
    )

    _LAYER_BY_ROLE = {
        RaterRole.PARENT: "parents",
        RaterRole.TEACHER: "teachers",
        RaterRole.PEER: "peers",
    }

    # Ключ — ПАРА (группа, ученик), а не один ученик: один и тот же ребёнок
    # может попасть в кампанию и классом, и кейсом (пары сливаются, но анкеты
    # остаются разными — см. generate_assessments). Тогда он показывается в
    # ОБЕИХ строках, и в каждой считаются только её собственные анкеты.
    # С ключом по ученику первая же встреченная анкета «застолбила» бы группу,
    # а строка кейса осталась бы с ненулевым счётчиком и пустым списком —
    # то есть не раскрывалась бы вовсе.
    students: dict[tuple[CoverageKey, int], dict] = {}

    for (
        class_id,
        case_id,
        subject_id,
        respondent_id,
        rater_role,
        status,
        subject,
        respondent_name,
    ) in rows.all():
        key = (coverage_key(class_id, case_id), subject_id)
        row = students.get(key)
        if row is None:
            row = students[key] = {
                "subject": subject,
                "self_status": None,
                "parents": {"total": 0, "completed": 0, "raters": []},
                "teachers": {"total": 0, "completed": 0, "raters": []},
                "peers": {"total": 0, "completed": 0, "raters": []},
            }

        if respondent_id == subject_id:
            row["self_status"] = status
            continue

        layer = row.get(_LAYER_BY_ROLE.get(rater_role, ""))
        if layer is None:
            continue
        layer["total"] += 1
        if status == AssessmentStatus.COMPLETED:
            layer["completed"] += 1
        layer["raters"].append(
            {"id": respondent_id, "full_name": respondent_name, "status": status}
        )

    by_group: dict[CoverageKey, list[dict]] = {}
    # Порядок внутри группы — по имени, как в get_class_roster: один и тот же
    # класс на двух экранах должен читаться одинаково.
    for key in sorted(students, key=lambda k: students[k]["subject"].full_name):
        group_key, _subject_id = key
        row = students[key]
        # Внутри слоя — незаполненные первыми: раскрывают его именно затем,
        # чтобы понять, кому напомнить, и искать их среди готовых незачем.
        for layer_name in ("parents", "teachers", "peers"):
            row[layer_name]["raters"].sort(
                key=lambda r: (r["status"] == AssessmentStatus.COMPLETED, r["full_name"])
            )
        by_group.setdefault(group_key, []).append(row)
    return by_group


async def previous_campaign_by_subject(
    db: AsyncSession, subject_ids: set[int], period_year: int, period_month: int
) -> dict[int, int]:
    """subject_id → id его предыдущей кампании, одним запросом на весь класс.

    Батч-версия previous_campaign_id_for_subject: на экране учителя строк
    столько же, сколько учеников, и запрос на каждого дал бы N+1.

    Предыдущий период ищем ПО СУБЪЕКТУ, а не по классу: при переводе класс
    меняется (нынешний 8-1 в прошлом году был 7-1), и поиск по class_id не
    нашёл бы прошлогоднюю кампанию вовсе.
    """
    if not subject_ids:
        return {}

    # "Строго раньше" отсекается в БД кортежным сравнением (год, месяц) — так
    # же, как в поштучной previous_campaign_id_for_subject. А вот "самая
    # свежая из оставшихся ПО КАЖДОМУ субъекту" считается в Python: это
    # group-by-максимум, в SQL он потребовал бы DISTINCT ON или оконной
    # функции ради выборки, где кампаний на субъекта единицы.
    rows = await db.execute(
        select(
            Assessment.subject_id,
            Assessment.campaign_id,
            Campaign.period_year,
            Campaign.period_month,
        )
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(
            Assessment.subject_id.in_(subject_ids),
            Campaign.status == CampaignStatus.CLOSED,
            tuple_(Campaign.period_year, Campaign.period_month) < tuple_(period_year, period_month),
        )
        .distinct()
    )

    best: dict[int, tuple[int, int, int]] = {}
    for subject_id, campaign_id, row_year, row_month in rows.all():
        candidate = (row_year, row_month, campaign_id)
        if subject_id not in best or candidate > best[subject_id]:
            best[subject_id] = candidate

    return {subject_id: candidate[2] for subject_id, candidate in best.items()}


async def assessment_progress_by_subject(
    db: AsyncSession, campaign_id: int, subject_ids: set[int]
) -> dict[int, dict]:
    """subject_id → {total, completed, self_status} по анкетам ПРО ученика.

    Самооценку выделяем по respondent_id == subject_id, а не по rater_role:
    оба варианта равнозначны по данным, но сравнение id не зависит от того,
    проставлена ли роль в архивных анкетах.
    """
    if not subject_ids:
        return {}

    rows = await db.execute(
        select(
            Assessment.subject_id,
            Assessment.respondent_id,
            Assessment.status,
        ).where(
            Assessment.campaign_id == campaign_id,
            Assessment.subject_id.in_(subject_ids),
        )
    )

    progress: dict[int, dict] = {
        subject_id: {"total": 0, "completed": 0, "self_status": None} for subject_id in subject_ids
    }
    for subject_id, respondent_id, status in rows.all():
        row = progress[subject_id]
        row["total"] += 1
        if status == AssessmentStatus.COMPLETED:
            row["completed"] += 1
        if respondent_id == subject_id:
            row["self_status"] = status
    return progress


async def load_subject_with_viewers(db: AsyncSession, subject_id: int) -> User | None:
    """Субъект вместе со связями, которые решают, кому можно смотреть его
    результаты: учителя класса, руководители кейса, родители.

    Сама проверка прав — в service: репозиторий отдаёт данные, решение о
    доступе принимает слой выше.
    """
    query = await db.execute(
        select(User)
        .where(User.id == subject_id)
        .options(
            selectinload(User.school_class).selectinload(SchoolClass.teachers),
            selectinload(User.case).selectinload(Case.teachers),
            selectinload(User.parents),
        )
    )
    return query.scalar_one_or_none()


async def latest_campaign_id_for_group(
    db: AsyncSession,
    snapshot_column: InstrumentedAttribute,
    group_id: int,
    only_completed: bool = True,
) -> int | None:
    """Самая свежая кампания, где у группы (класса или кейса) есть анкеты —
    по снапшоту, а не по текущей привязке учеников.

    Сортировка по периоду, а не по id: архив прошлого года импортируется
    позже текущего и получает БОЛЬШИЙ id, поэтому id хронологию не отражает.

    `only_completed=True` (профиль класса/кейса) — только завершённые
    кампании. Экраны МОНИТОРИНГА хода диагностики (состав класса с
    прогрессом, покрытие) передают False: там смысл как раз в текущей,
    незакрытой кампании — иначе учитель во время диагностики видел бы
    прошлый год и не понимал, по кому анкеты ещё не заполнены.
    """
    query = (
        select(Assessment.campaign_id)
        .join(Campaign, Campaign.id == Assessment.campaign_id)
        .where(snapshot_column == group_id)
        .order_by(
            Campaign.period_year.desc(),
            Campaign.period_month.desc(),
            Assessment.campaign_id.desc(),
        )
        .limit(1)
    )
    if only_completed:
        query = query.where(Campaign.status == CampaignStatus.CLOSED)
    row = await db.execute(query)
    return row.scalar_one_or_none()


async def closed_campaign_ids_in_period(db: AsyncSession, campaign: Campaign) -> set[int]:
    """Все завершённые кампании того же периода — это и есть «школа».

    Не одна кампания: в боевых данных кампанию заводят на каждый класс
    отдельно, поэтому внутри одной кампании «школа» вырождается в этот же
    класс и сравнение всегда даёт ноль.
    """
    rows = await db.execute(
        select(Campaign.id).where(
            Campaign.period_year == campaign.period_year,
            Campaign.period_month == campaign.period_month,
            Campaign.status == CampaignStatus.CLOSED,
        )
    )
    return set(rows.scalars())


async def list_competencies(db: AsyncSession) -> list[Competency]:
    """Справочник критериев в порядке методики — для раскладки ответа."""
    rows = await db.execute(select(Competency).order_by(Competency.order))
    return list(rows.scalars().all())


async def get_campaign(db: AsyncSession, campaign_id: int) -> Campaign | None:
    """Кампания по id (или None). Отдельная функция, чтобы service не
    импортировал модель ради одного db.get."""
    return await db.get(Campaign, campaign_id)


async def list_closed_campaigns_for_subject(db: AsyncSession, subject_id: int) -> list[Campaign]:
    """Завершённые кампании субъекта, свежие сверху — под переключатель
    периодов. Только завершённые: список обязан совпадать с тем, что страница
    результатов реально умеет открыть, иначе выбор периода давал бы 409."""
    rows = await db.execute(
        select(Campaign)
        .join(Assessment, Assessment.campaign_id == Campaign.id)
        .where(Assessment.subject_id == subject_id)
        .where(Campaign.status == CampaignStatus.CLOSED)
        .distinct()
        .order_by(Campaign.period_year.desc(), Campaign.period_month.desc(), Campaign.id.desc())
    )
    return list(rows.scalars())


async def questionnaire_version_note(db: AsyncSession, version_id: int) -> str | None:
    """Текст оговорки редакции анкеты («формулировки изменились»). Придумывать
    его в коде нельзя — он лежит в самой редакции."""
    return await db.scalar(
        select(QuestionnaireVersion.note).where(QuestionnaireVersion.id == version_id)
    )


async def load_class_with_teachers(db: AsyncSession, class_id: int) -> SchoolClass | None:
    """Класс вместе с учителями — для проверки прав на профиль класса."""
    rows = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id == class_id)
        .options(selectinload(SchoolClass.teachers))
    )
    return rows.scalar_one_or_none()


async def load_class_with_roster(db: AsyncSession, class_id: int) -> SchoolClass | None:
    """Класс с учителями И учениками — для экрана состава: там нужны и права,
    и текущий список, чтобы показать тех, кому анкету не выдали вовсе."""
    rows = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id == class_id)
        .options(selectinload(SchoolClass.teachers), selectinload(SchoolClass.students))
    )
    return rows.scalar_one_or_none()


async def load_case_with_teachers(db: AsyncSession, case_id: int) -> Case | None:
    """Кейс вместе с руководителями — для проверки прав на профиль кейса."""
    rows = await db.execute(
        select(Case).where(Case.id == case_id).options(selectinload(Case.teachers))
    )
    return rows.scalar_one_or_none()


async def coverage_rows_by_snapshot(db: AsyncSession, campaign_id: int) -> list[tuple]:
    """Сырые счётчики покрытия: (class_id, case_id, total, completed, grade,
    section, case_name) по парам снапшотов.

    Схлопывать пары в группы — задача вызывающего: у анкет одного кейса
    subject_class_id разный (ученики кружка из разных классов), поэтому на
    одну группу GROUP BY даёт несколько строк.
    """
    completed = func.count().filter(Assessment.status == AssessmentStatus.COMPLETED)
    rows = await db.execute(
        select(
            Assessment.subject_class_id,
            Assessment.subject_case_id,
            func.count().label("total"),
            completed.label("completed"),
            SchoolClass.grade,
            SchoolClass.section,
            Case.name,
        )
        .outerjoin(SchoolClass, SchoolClass.id == Assessment.subject_class_id)
        .outerjoin(Case, Case.id == Assessment.subject_case_id)
        .where(Assessment.campaign_id == campaign_id)
        .group_by(
            Assessment.subject_class_id,
            Assessment.subject_case_id,
            SchoolClass.grade,
            SchoolClass.section,
            Case.name,
        )
    )
    return list(rows.all())


async def load_users(db: AsyncSession, user_ids: set[int]) -> list[User]:
    """Пользователи пачкой по id — для раскладки имён в строках экрана."""
    rows = await db.execute(select(User).where(User.id.in_(user_ids)))
    return list(rows.scalars())
