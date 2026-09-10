"""Оркестрация результатов: права + сборка ответа эндпоинта.

Модуль разложен на три файла (Этап 5 разросся до полутора тысяч строк):
domain.py — чистые правила без БД, repository.py — запросы, service.py —
то, что связывает их вместе и решает, кому что показывать.

Права считаются по ТЕКУЩИМ связям (доступ определяется тем, кто учитель и
родитель сейчас), а роли оценивающих в агрегации берутся зафиксированные
при генерации — см. repository.load_scored_answers.
"""

from collections.abc import Collection

from sqlalchemy.ext.asyncio import AsyncSession

from vektor.modules.assessments.errors import CampaignNotFound
from vektor.modules.assessments.models import Assessment
from vektor.modules.cases.errors import CaseNotFound
from vektor.modules.classes.errors import ClassNotFound
from vektor.modules.results import repository as repo
from vektor.modules.results.domain import (
    CoverageKey,
    aggregate_by_competency_and_rater,
    average_profiles,
    can_view_group_results,
    can_view_results,
    compute_deltas,
    compute_gap,
    core_average,
    count_peer_raters_by_competency,
    coverage_key,
    coverage_sort_key,
    others_by_competency,
    overall_by_competency,
    pick_growth_zones,
    rank_school_gaps,
    rank_self_gaps,
    redact_peer_scores,
    self_by_competency,
    shared_competencies,
)
from vektor.modules.results.errors import (
    ClassHasNoDiagnostics,
    NotAllowedToViewResults,
    SubjectNotFound,
)
from vektor.modules.users.models import User
from vektor.shared.class_label import class_label
from vektor.shared.enums import CampaignStatus, RaterRole


async def _load_subject_for_results(db: AsyncSession, subject_id: int, current_user: User) -> User:
    """Загрузить субъекта и проверить право текущего пользователя на его
    результаты. Общая точка для страницы результатов и динамики: иначе
    динамика могла бы разойтись с ней в правах и показать чужие баллы.
    """
    subject = await repo.load_subject_with_viewers(db, subject_id)
    if subject is None:
        raise SubjectNotFound()

    # Учителя КЛАССА и учителя КЕЙСА равноправны: руководитель кружка ведёт
    # ученика ничуть не меньше предметника, а ученики кейса по определению из
    # разных классов — без этого объединения он не увидел бы результаты
    # собственных подопечных (решение заказчика от 2026-09-02).
    teacher_ids = {t.id for t in subject.school_class.teachers} if subject.school_class else set()
    if subject.case:
        teacher_ids |= {t.id for t in subject.case.teachers}
    parent_ids = {p.id for p in subject.parents}

    if not can_view_results(
        current_user.id, current_user.role, subject_id, teacher_ids, parent_ids
    ):
        raise NotAllowedToViewResults()

    return subject


async def latest_campaign_id_for_subject(db: AsyncSession, subject_id: int) -> int | None:
    """Последняя кампания субъекта — под запрос без явного campaign_id."""
    return await repo.latest_campaign_id_for_subject(db, subject_id)


async def latest_campaign_id_for_class(
    db: AsyncSession,
    class_id: int,
    only_completed: bool = True,
    subject_ids: Collection[int] | None = None,
) -> int | None:
    """Последняя кампания класса. Обёртка над общей репозиторной функцией:
    класс и кейс отличаются только колонкой снапшота."""
    return await repo.latest_campaign_id_for_group(
        db, Assessment.subject_class_id, class_id, only_completed, subject_ids
    )


async def latest_campaign_id_for_case(
    db: AsyncSession, case_id: int, only_completed: bool = True
) -> int | None:
    """Последняя кампания кейса — см. latest_campaign_id_for_class."""
    return await repo.latest_campaign_id_for_group(
        db, Assessment.subject_case_id, case_id, only_completed
    )


async def previous_campaign_id_for_subject(
    db: AsyncSession, subject_id: int, campaign_id: int
) -> int | None:
    """Предыдущий период того же субъекта — под динамику."""
    return await repo.previous_campaign_id_for_subject(db, subject_id, campaign_id)


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
    # Права проверяем ПЕРВЫМИ, статус кампании — вторым: посторонний не
    # должен по коду ошибки узнавать, есть ли у чужого ученика незавершённая
    # диагностика.
    subject = await _load_subject_for_results(db, subject_id, current_user)
    await repo.load_completed_campaign(db, campaign_id)

    scored_answers = await repo.load_scored_answers(db, subject_id, campaign_id)

    peer_rater_counts = count_peer_raters_by_competency(scored_answers)
    raw_scores = aggregate_by_competency_and_rater(scored_answers)
    # С этой строки и ниже работаем ТОЛЬКО с безопасными данными.
    role_scores = redact_peer_scores(raw_scores, peer_rater_counts)

    overall_scores = overall_by_competency(role_scores)
    self_scores = self_by_competency(role_scores)
    others_scores = others_by_competency(role_scores)
    gaps = compute_gap(self_scores, others_scores)
    growth_zone_ids = pick_growth_zones(overall_scores)

    competencies = await repo.list_competencies(db)
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


async def list_subject_campaigns(
    db: AsyncSession, subject_id: int, current_user: User
) -> list[dict]:
    """Периоды, за которые у субъекта вообще есть результаты — под переключатель
    кампаний на экране результатов. Порядок хронологический по периоду
    (см. latest_campaign_id_for_subject: id ≠ хронология).

    Только завершённые кампании — список должен совпадать с тем, что
    страница результатов реально умеет открыть, иначе выбор периода в
    селекторе приводил бы к 409."""
    await _load_subject_for_results(db, subject_id, current_user)

    return [
        {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "period_year": campaign.period_year,
            "period_month": campaign.period_month,
            "status": campaign.status,
        }
        for campaign in await repo.list_closed_campaigns_for_subject(db, subject_id)
    ]


async def get_subject_dynamics(
    db: AsyncSession, subject_id: int, campaign_id: int, current_user: User
) -> dict:
    """Сравнение текущего периода с предыдущим по общему ядру критериев.

    Отсутствие предыдущего периода — НЕ ошибка: у пятиклассников прошлогодних
    данных нет в принципе. Возвращаем текущие баллы и previous_campaign_id=None,
    фронт сам решает, рисовать ли стрелку.
    """
    subject = await _load_subject_for_results(db, subject_id, current_user)
    campaign = await repo.load_completed_campaign(db, campaign_id)

    current_scores = await repo.overall_scores_for(db, subject_id, campaign_id)

    previous_id = await repo.previous_campaign_id_for_subject(db, subject_id, campaign_id)
    previous_campaign = await repo.get_campaign(db, previous_id) if previous_id else None
    previous_scores = (
        await repo.overall_scores_for(db, subject_id, previous_id) if previous_id else {}
    )

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
        version_note = await repo.questionnaire_version_note(
            db, previous_campaign.questionnaire_version_id
        )

    competencies = await repo.list_competencies(db)

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
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
        "previous_campaign_id": previous_id,
        "previous_campaign_title": previous_campaign.title if previous_campaign else None,
        "previous_campaign_period_year": (
            previous_campaign.period_year if previous_campaign else None
        ),
        "previous_campaign_period_month": (
            previous_campaign.period_month if previous_campaign else None
        ),
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


async def _class_cohort_subject_ids(
    db: AsyncSession, campaign_id: int, class_id: int, current_student_ids: Collection[int]
) -> set[int]:
    """Кого считать «этим классом» в этой кампании — ЕДИНСТВЕННОЕ место, где
    это решается: профиль, динамика и состав обязаны брать одних и тех же
    детей, иначе радар нарисован по одной группе, а таблица под ним по другой.

    Слагаемых два, и оба нужны, потому что «класс» в данных двусмыслен по
    построению: школа переиспользует строки классов из года в год (перевод
    меняет ученику school_class_id, а не заводит новый SchoolClass).

    1. Снапшот `Assessment.subject_class_id` — кому анкеты выдали ПО ЭТОЙ
       строке класса. Именно снапшот, а не текущая привязка: иначе выбывшие
       исчезли бы из прошлогодней диагностики и средние за тот год перестали
       бы сходиться.
    2. Нынешние ученики, участвовавшие в ЭТОЙ кампании под ДРУГИМ ярлыком:
       сегодняшний 8-1 год назад проходил диагностику как 7-1. Без второго
       слагаемого выбор прошлого периода давал бы пустой экран вместо истории
       собственного класса — ровно тот баг, из-за которого правило и свели
       в одну функцию.
    """
    class_map = await repo.subject_group_map(db, campaign_id, Assessment.subject_class_id)
    subject_ids = {sid for sid, cid in class_map.items() if cid == class_id}
    return subject_ids | (set(current_student_ids) & set(class_map))


async def _case_subject_ids(db: AsyncSession, campaign_id: int, case_id: int) -> set[int]:
    """Состав кейса в кампании — чистый снапшот, без «нынешних участников».

    Двусмысленности класса тут нет: строку класса школа переиспользует под
    новый набор целиком, а кружок живёт дальше со своим именем и меняет
    состав постепенно. Второе слагаемое поэтому было бы почти всегда no-op,
    но подмешивало бы в архив кружка сегодняшних участников.
    """
    case_map = await repo.subject_group_map(db, campaign_id, Assessment.subject_case_id)
    return {sid for sid, cid in case_map.items() if cid == case_id}


async def _group_profile(
    db: AsyncSession,
    campaign_id: int,
    subject_ids: set[int],
    score_key: str,
) -> dict:
    """Профиль группы за ОДНУ кампанию: класс и кейс считаются ОДИНАКОВО.

    Группу принимаем уже готовым списком учеников, а не парой «колонка
    снапшота + id»: кто входит в группу — вопрос класса и кейса, и он у них
    разный (см. _class_cohort_subject_ids против _case_subject_ids), а как
    считается профиль — вопрос один на всех. Развести эти два вопроса и есть
    смысл этой сигнатуры: раньше сюда протекало правило состава, и оно
    разъехалось с тем, по которому собирался состав на экране.

    Права и загрузка самой группы остаются у вызывающего: они у класса и
    кейса разные (SchoolClass против Case), и подмешивать их сюда значило бы
    протащить сюда же оба модуля.
    """
    campaign = await repo.load_completed_campaign(db, campaign_id)

    # «Школа» — весь ПЕРИОД, а не одна кампания: в боевых данных кампанию
    # заводят на каждый класс/кейс отдельно, поэтому внутри одной кампании
    # школа выродилась бы в саму же группу и сравнение всегда давало бы ноль.
    campaign_ids = await repo.closed_campaign_ids_in_period(db, campaign)

    all_profiles = await repo.profiles_by_campaign_and_subject(db, campaign_ids)
    # Профили строим ПОВЕРХ индивидуальных, а не отдельным запросом по сырым
    # ответам: иначе правило анонимности пришлось бы применять второй раз, в
    # другом месте и по другой формуле.
    group_profiles = [
        profile
        for (cid, sid), profile in all_profiles.items()
        if cid == campaign_id and sid in subject_ids and profile.overall
    ]
    school_profiles = [profile for profile in all_profiles.values() if profile.overall]

    return {
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
        "students_total": len(subject_ids),
        **await _profile_payload(db, group_profiles, school_profiles, score_key),
    }


async def _profile_payload(
    db: AsyncSession,
    group_profiles: list,
    school_profiles: list,
    score_key: str,
) -> dict:
    """Сборка ответа из уже отобранных профилей — общая для класса и кейса.

    Кто попал в группу, решает вызывающий; всё, что дальше, — здесь и только
    здесь: разъехавшись, две копии дали бы двум экранам разные числа по одним
    данным.
    """
    # Среднее ПО УЧЕНИКАМ (каждый весит одинаково), а не по ответам: иначе
    # ученик, про которого ответили пятеро, перевесил бы того, про кого
    # ответил один.
    group_scores = average_profiles([p.overall for p in group_profiles])
    school_scores = average_profiles([p.overall for p in school_profiles])

    # Слои усредняются ПО ТЕМ ЖЕ правилам, что итог: ученик весит одинаково,
    # а критерий, которого у него нет, просто не участвует.
    group_self = average_profiles([p.self_scores for p in group_profiles])
    group_others = average_profiles([p.others_scores for p in group_profiles])

    school_gaps = rank_school_gaps(group_scores, school_scores)
    self_gaps = rank_self_gaps(group_self, group_others)

    competencies = await repo.list_competencies(db)
    competencies_by_id = {c.id: c for c in competencies}

    return {
        "students_with_results": len(group_profiles),
        "average": sum(group_scores.values()) / len(group_scores) if group_scores else None,
        "school_average": (
            sum(school_scores.values()) / len(school_scores) if school_scores else None
        ),
        "competencies": [
            {
                "competency_id": comp.id,
                "code": comp.code,
                "name": comp.name,
                score_key: group_scores.get(comp.id),
                "school_avg": school_scores.get(comp.id),
            }
            for comp in competencies
            if comp.id in group_scores or comp.id in school_scores
        ],
        "school_gaps": [
            {
                "competency_id": competency_id,
                "code": competencies_by_id[competency_id].code,
                "name": competencies_by_id[competency_id].name,
                "delta": delta,
                score_key: group_scores.get(competency_id),
                "school_avg": school_scores.get(competency_id),
            }
            for competency_id, delta in school_gaps
        ],
        "self_gaps": [
            {
                "competency_id": competency_id,
                "code": competencies_by_id[competency_id].code,
                "name": competencies_by_id[competency_id].name,
                "gap": gap,
                "self_avg": group_self.get(competency_id),
                "others_avg": group_others.get(competency_id),
            }
            for competency_id, gap in self_gaps
        ],
    }


async def get_class_results(
    db: AsyncSession, class_id: int, campaign_id: int, current_user: User
) -> dict:
    """Средний профиль класса, сравнение со школой и зоны роста класса.

    Период ОБЯЗАТЕЛЕН и приходит явным id. Раньше без него экран считал
    «нынешний состав по последней диагностике каждого ученика» — второй режим
    со своим составом, своей школой для сравнения и своим пустым состоянием,
    из-за которого профиль и таблица под ним могли показывать разных детей.
    Выбор периода живёт на экране (переключатель + список из
    `list_class_campaigns`), и он же теперь единственное место, где решается,
    какой период открыт по умолчанию.
    """
    school_class = await repo.load_class_with_roster(db, class_id)
    if school_class is None:
        raise ClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    subject_ids = await _class_cohort_subject_ids(
        db, campaign_id, class_id, {student.id for student in school_class.students}
    )
    profile = await _group_profile(db, campaign_id, subject_ids, "class_avg")
    return {
        "class_id": class_id,
        "class_label": class_label(school_class.grade, school_class.section),
        "class_average": profile.pop("average"),
        **profile,
    }


async def get_case_results(
    db: AsyncSession, case_id: int, campaign_id: int, current_user: User
) -> dict:
    """Средний профиль кейса, сравнение со школой и зоны роста кейса.

    Кейс сравнивается со ШКОЛОЙ, а не с классами участников: учеников кружка
    набирают из разных классов, и «свой класс» у группы не определён.
    """
    case = await repo.load_case_with_teachers(db, case_id)
    if case is None:
        raise CaseNotFound()

    # Право то же, что на класс: руководитель кейса уже видит своих учеников
    # поштучно (решение заказчика от 2026-09-02), группа целиком — не больше.
    teacher_ids = {t.id for t in case.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    subject_ids = await _case_subject_ids(db, campaign_id, case_id)
    profile = await _group_profile(db, campaign_id, subject_ids, "case_avg")
    return {
        "case_id": case_id,
        "case_name": case.name,
        "case_average": profile.pop("average"),
        **profile,
    }


async def _latest_campaign_of(db: AsyncSession, campaign_ids: set[int]):
    """Самая свежая кампания из набора — под ярлык периода в ответе."""
    if not campaign_ids:
        return None
    candidates = [await repo.get_campaign(db, cid) for cid in campaign_ids]
    return max(
        (c for c in candidates if c is not None),
        key=lambda c: (c.period_year, c.period_month, c.id),
        default=None,
    )


async def _group_dynamics(
    db: AsyncSession,
    campaign_id: int,
    subject_ids: set[int],
) -> dict:
    """Динамика группы за ОДНУ выбранную кампанию: её период против
    предыдущего. Состав приходит готовым — тем же, что у `_group_profile`,
    иначе радар и столбики под ним считались бы по разным детям.
    """
    campaign = await repo.load_completed_campaign(db, campaign_id)

    previous_ids = await repo.previous_campaign_by_subject(
        db, subject_ids, campaign.period_year, campaign.period_month
    )
    return await _dynamics_payload(
        db,
        subject_ids,
        current_ids={sid: campaign_id for sid in subject_ids},
        previous_ids=previous_ids,
    )


async def _dynamics_payload(
    db: AsyncSession,
    subject_ids: set[int],
    current_ids: dict[int, int],
    previous_ids: dict[int, int],
) -> dict:
    """Расчёт динамики из уже отобранных пар «сейчас / тогда».

    Два правила, без которых сравнение врёт, живут здесь и только здесь:

    1. **Сравниваем ОДНИХ И ТЕХ ЖЕ учеников.** В обе средние идут только те,
       у кого есть оба периода, — иначе пришедший в этом году новичок сдвигал
       бы «текущее» и разница читалась бы как рост коллектива. Предыдущая
       кампания при этом ищется по СУБЪЕКТУ, а не по группе: нынешний 8-1 в
       прошлом году был 7-1, и поиск по id класса не нашёл бы ничего.

    2. **Дельты только по общему ядру критериев.** Состав меняется
       (профпробы открываются с 9 класса), и появившийся критерий показываем
       со значением, но без дельты — иначе смена состава анкеты прочиталась
       бы как прирост.
    """
    profiles = await repo.profiles_by_campaign_and_subject(
        db, set(current_ids.values()) | set(previous_ids.values())
    )

    # Пары «сейчас / тогда» по каждому ученику: обе половины должны быть
    # непустыми, иначе это не сравнение.
    current_profiles: list[dict[int, float]] = []
    previous_profiles: list[dict[int, float]] = []
    compared_previous_campaigns: set[int] = set()
    for subject_id in subject_ids:
        current_id = current_ids.get(subject_id)
        current = profiles.get((current_id, subject_id)) if current_id else None
        previous_id = previous_ids.get(subject_id)
        previous = profiles.get((previous_id, subject_id)) if previous_id else None
        if current is None or previous is None or not current.overall or not previous.overall:
            continue
        current_profiles.append(current.overall)
        previous_profiles.append(previous.overall)
        compared_previous_campaigns.add(previous_id)

    if not current_profiles:
        # Прошлого периода нет ни у кого (пятиклассники, первый год кружка) —
        # отдаём текущие баллы по всему составу без дельт. Пустой ответ здесь
        # был бы неотличим от «результатов нет вовсе».
        current_profiles = [
            profile.overall
            for sid, cid in current_ids.items()
            if (profile := profiles.get((cid, sid))) is not None and profile.overall
        ]

    current_scores = average_profiles(current_profiles)
    previous_scores = average_profiles(previous_profiles)
    core = shared_competencies(current_scores, previous_scores)
    deltas = compute_deltas(current_scores, previous_scores, core)

    # Ярлык периода — по САМОЙ СВЕЖЕЙ из использованных кампаний, отдельно для
    # текущей половины и для прошлой. В режиме одной кампании это она сама; в
    # сшитом у разных учеников кампании разные (10-й класс собран из двух
    # девятых), и любая одна в заголовке была бы враньём про остальных.
    campaign = await _latest_campaign_of(db, set(current_ids.values()))
    previous_campaign = await _latest_campaign_of(db, compared_previous_campaigns)

    # Оговорка о смене редакции — как в get_subject_dynamics: текст берём из
    # самой редакции, придумывать его здесь нельзя.
    versions_differ = bool(
        campaign
        and previous_campaign
        and previous_campaign.questionnaire_version_id != campaign.questionnaire_version_id
    )
    version_note = None
    if versions_differ and previous_campaign:
        version_note = await repo.questionnaire_version_note(
            db, previous_campaign.questionnaire_version_id
        )

    competencies = await repo.list_competencies(db)
    current_core_average = core_average(current_scores, core)
    previous_core_average = core_average(previous_scores, core)

    return {
        "campaign_id": campaign.id if campaign else None,
        "campaign_title": campaign.title if campaign else None,
        "campaign_period_year": campaign.period_year if campaign else None,
        "campaign_period_month": campaign.period_month if campaign else None,
        "previous_campaign_id": previous_campaign.id if previous_campaign else None,
        "previous_campaign_period_year": (
            previous_campaign.period_year if previous_campaign else None
        ),
        "previous_campaign_period_month": (
            previous_campaign.period_month if previous_campaign else None
        ),
        # Сколько учеников реально попало в сравнение и сколько их в группе
        # вообще: числа расходятся у классов, куда кто-то пришёл в этом году,
        # и это надо показывать, а не прятать.
        "students_compared": len(previous_profiles),
        "students_total": len(subject_ids),
        "versions_differ": versions_differ,
        "version_note": version_note,
        "core_competencies_count": len(core),
        "core_average": current_core_average,
        "previous_core_average": previous_core_average,
        "core_average_delta": (
            current_core_average - previous_core_average
            if current_core_average is not None and previous_core_average is not None
            else None
        ),
        "competencies": [
            {
                "competency_id": comp.id,
                "code": comp.code,
                "name": comp.name,
                "overall_avg": current_scores.get(comp.id),
                "previous_avg": previous_scores.get(comp.id),
                "delta": deltas.get(comp.id),
                "in_core": comp.id in core,
            }
            for comp in competencies
            if comp.id in current_scores or comp.id in previous_scores
        ],
    }


async def get_class_dynamics(
    db: AsyncSession, class_id: int, campaign_id: int, current_user: User
) -> dict:
    """Динамика класса по критериям. Права и период — как у профиля класса:
    период обязателен и приходит явным id."""
    school_class = await repo.load_class_with_roster(db, class_id)
    if school_class is None:
        raise ClassNotFound()
    if not can_view_group_results(
        current_user.id, current_user.role, {t.id for t in school_class.teachers}
    ):
        raise NotAllowedToViewResults()

    # Состав — тот же, что у профиля класса, и той же функцией: динамика
    # рисуется под радаром, и считать их по разным детям нельзя.
    subject_ids = await _class_cohort_subject_ids(
        db, campaign_id, class_id, {student.id for student in school_class.students}
    )
    dynamics = await _group_dynamics(db, campaign_id, subject_ids)
    return {
        "class_id": class_id,
        "class_label": class_label(school_class.grade, school_class.section),
        **dynamics,
    }


async def get_case_dynamics(
    db: AsyncSession, case_id: int, campaign_id: int, current_user: User
) -> dict:
    """Динамика кейса по критериям. Права те же, что у профиля кейса."""
    case = await repo.load_case_with_teachers(db, case_id)
    if case is None:
        raise CaseNotFound()
    if not can_view_group_results(
        current_user.id, current_user.role, {t.id for t in case.teachers}
    ):
        raise NotAllowedToViewResults()

    subject_ids = await _case_subject_ids(db, campaign_id, case_id)
    dynamics = await _group_dynamics(db, campaign_id, subject_ids)
    return {
        "case_id": case_id,
        "case_name": case.name,
        **dynamics,
    }


# Ключ строки покрытия: («class», id) | («case», id) | («none», None).
# Кортеж, а не голый id: нумерация классов и кейсов независима, и class_id=3
# с case_id=3 — разные строки.
async def get_campaign_coverage(db: AsyncSession, campaign_id: int) -> dict:
    """«X из Y анкет» по классам и кейсам + детализация по ученикам —
    админский экран кампании.

    Группируем по ОСНОВАНИЮ выдачи (coverage_key): анкета попадает ровно в
    одну строку, поэтому сумма строк равна общему числу анкет кампании.
    Анкеты без снапшотов вовсе (субъект вне класса, пилотная кампания на
    учителях) попадают в строку kind="none", а не выбрасываются: иначе итог
    не сходился бы.

    Детализация по ученикам (self / parents / teachers / peers) считается
    ЗДЕСЬ ЖЕ, из тех же анкет, а не отдельным эндпоинтом: числа шапки и числа
    внутри строки обязаны сходиться, а два независимых прохода по одним и тем
    же данным расходятся (см. 5e про агрегаты поверх профилей).
    """
    campaign = await repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    rows = await repo.coverage_rows_by_snapshot(db, campaign_id)
    students_by_group = await repo.campaign_students_by_group(db, campaign_id)

    # Один ключ может прийти НЕСКОЛЬКИМИ строками SQL: у анкет одного кейса
    # subject_class_id разный (ученики кружка из разных классов), а группа —
    # одна. Поэтому схлопываем в Python, а не полагаемся на GROUP BY.
    groups: dict[CoverageKey, dict] = {}
    total_all = 0
    completed_all = 0
    for class_id, case_id, total, done, grade, section, case_name in rows:
        total_all += total
        completed_all += done
        key = coverage_key(class_id, case_id)
        group = groups.get(key)
        if group is None:
            kind, _ = key
            group = groups[key] = {
                "kind": kind,
                # У строки кейса класс не указываем вовсе, хотя на анкетах он
                # проставлен: ученики кружка из разных классов, и любой один
                # из них в заголовке строки был бы враньём.
                "class_id": class_id if kind == "class" else None,
                "class_label": class_label(grade, section) if kind == "class" else None,
                "case_id": case_id if kind == "case" else None,
                "case_name": case_name if kind == "case" else None,
                "total": 0,
                "completed": 0,
                "students": students_by_group.get(key, []),
            }
        group["total"] += total
        group["completed"] += done

    groups_out = [
        {
            **group,
            "percent": round(group["completed"] / group["total"] * 100, 1)
            if group["total"]
            else 0.0,
        }
        for group in sorted(groups.values(), key=coverage_sort_key)
    ]

    return {
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
        "total": total_all,
        "completed": completed_all,
        "percent": round(completed_all / total_all * 100, 1) if total_all else 0.0,
        "groups": groups_out,
    }


async def _resolve_class_campaign(db: AsyncSession, class_id: int, campaign_id: int | None) -> int:
    """Кампания для экранов класса: явная либо «последняя у ЭТОЙ когорты».

    Ключевое слово — когорта. Школа переиспользует строки классов из года в
    год (перевод меняет ученику school_class_id, а не заводит новый
    SchoolClass), поэтому «последняя кампания класса 5-2» вполне может
    относиться к детям, которых в нём давно нет: к прошлогодним
    пятиклассникам, ныне шестиклассникам, вместе с выбывшими из школы.
    Открывать такое по умолчанию нельзя — ни учителю, ни админу: экран
    выглядит рабочим, а показывает чужих людей.

    Архив никуда не девается и открывается явным campaign_id — их список
    отдаёт `list_class_campaigns`, на нём и построен переключатель периодов.
    """
    if campaign_id is not None:
        return campaign_id

    student_ids = await repo.student_ids_of_class(db, class_id)
    # Незавершённую кампанию берём тоже: единственный оставшийся потребитель —
    # состав класса с прогрессом, экран МОНИТОРИНГА, где смысл как раз в
    # идущей диагностике. Балльные экраны сюда не ходят вовсе: у них период
    # обязателен и приходит из переключателя. То же правило живёт и на фронте
    # (defaultCampaignId) — здесь оно остаётся ради прямых обращений к API и
    # первого запроса, когда список периодов ещё не загружен.
    resolved = await latest_campaign_id_for_class(
        db, class_id, only_completed=False, subject_ids=student_ids
    )
    if resolved is None:
        raise ClassHasNoDiagnostics()
    return resolved


async def list_class_campaigns(db: AsyncSession, class_id: int, current_user: User) -> list[dict]:
    """Периоды под переключатель на экране диагностики класса.

    Права те же, что у самого экрана: admin или учитель ЭТОГО класса —
    иначе список кампаний рассказывал бы постороннему, когда класс проходил
    диагностику.
    """
    school_class = await repo.load_class_with_roster(db, class_id)
    if school_class is None:
        raise ClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    student_ids = {student.id for student in school_class.students}
    return [
        {
            "campaign_id": campaign.id,
            "title": campaign.title,
            "period_year": campaign.period_year,
            "period_month": campaign.period_month,
            "status": campaign.status,
            # Чья это диагностика — нынешних детей или прошлого набора той же
            # строки класса. Без флага список выглядит как история одного
            # коллектива, хотя у 5-х классов это всегда чужая когорта.
            "is_current_cohort": is_current_cohort,
        }
        for campaign, is_current_cohort in await repo.list_campaigns_for_class(
            db, class_id, student_ids
        )
    ]


async def get_class_roster(
    db: AsyncSession, class_id: int, campaign_id: int | None, current_user: User
) -> dict:
    """Состав класса с прогрессом диагностики: строка на ученика (статус
    самооценки, собрано анкет, итоговый балл, динамика) плюс метрики шапки.

    Права те же, что у профиля класса: admin или учитель ЭТОГО класса.

    campaign_id=None — «последняя кампания ЭТОЙ когорты»: см. ниже, почему
    просто «последняя кампания класса» тут не годится.
    """
    school_class = await repo.load_class_with_roster(db, class_id)
    if school_class is None:
        raise ClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    student_ids = {student.id for student in school_class.students}

    # only_completed=False: это экран МОНИТОРИНГА, ему нужна и идущая
    # кампания — иначе во время диагностики учитель видел бы прошлый период
    # вместо того, по кому анкеты ещё не заполнены. Балльные экраны
    # (профиль, динамика) — наоборот, только завершённые.
    campaign_id = await _resolve_class_campaign(db, class_id, campaign_id)

    campaign = await repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    # Когорта класса в этой кампании — та же функция, что у профиля и
    # динамики: три экрана обязаны показывать одних и тех же детей.
    subject_ids = await _class_cohort_subject_ids(db, campaign_id, class_id, student_ids)

    # Плюс слагаемое, которое есть ТОЛЬКО у этого экрана: нынешние ученики
    # БЕЗ анкет, пока диагностика идёт, — тогда пустая строка означает
    # «анкету не выдали, разберитесь». Балльным экранам такой ученик не нужен
    # вовсе (баллов у него нет), а в закрытой кампании выдавать уже нечего:
    # подмешивание сегодняшнего состава к прошлому году склеивало бы две
    # когорты в одной таблице.
    if campaign.status != CampaignStatus.CLOSED:
        subject_ids |= student_ids

    progress = await repo.assessment_progress_by_subject(db, campaign_id, subject_ids)

    previous_campaign_ids = await repo.previous_campaign_by_subject(
        db, subject_ids, campaign.period_year, campaign.period_month
    )
    profiles = await repo.profiles_by_campaign_and_subject(
        db, {campaign_id} | set(previous_campaign_ids.values())
    )

    users = {user.id: user for user in await repo.load_users(db, subject_ids)}

    rows_out = []
    deltas: list[float] = []
    averages: list[float] = []
    for subject_id in sorted(subject_ids, key=lambda sid: users[sid].full_name):
        # Экрану состава нужен только итог; слои self/others профиль тоже
        # несёт, но здесь они ни к чему.
        current = profiles.get((campaign_id, subject_id))
        current_profile = current.overall if current else {}
        previous_id = previous_campaign_ids.get(subject_id)
        previous = profiles.get((previous_id, subject_id)) if previous_id else None
        previous_profile = previous.overall if previous else {}

        # Итог и дельта — по общему ядру критериев обоих периодов (как в
        # get_subject_dynamics): иначе появление возрастного критерия в 9
        # классе прочиталось бы как рост ученика.
        core = shared_competencies(current_profile, previous_profile)
        current_avg = (
            sum(current_profile.values()) / len(current_profile) if current_profile else None
        )
        previous_avg = core_average(previous_profile, core) if core else None
        current_core_avg = core_average(current_profile, core) if core else None
        delta = (
            round(current_core_avg - previous_avg, 3)
            if current_core_avg is not None and previous_avg is not None
            else None
        )

        if current_avg is not None:
            averages.append(current_avg)
        if delta is not None:
            deltas.append(delta)

        row = progress[subject_id]
        rows_out.append(
            {
                "subject": users[subject_id],
                "self_status": row["self_status"],
                "assessments_total": row["total"],
                "assessments_completed": row["completed"],
                "overall_avg": round(current_avg, 3) if current_avg is not None else None,
                "growth_zone_count": len(pick_growth_zones(current_profile)),
                "previous_overall_avg": (
                    round(previous_avg, 3) if previous_avg is not None else None
                ),
                "delta": delta,
            }
        )

    total_all = sum(row["assessments_total"] for row in rows_out)
    completed_all = sum(row["assessments_completed"] for row in rows_out)

    return {
        "class_id": class_id,
        "class_label": class_label(school_class.grade, school_class.section),
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
        # Статус отдаём сырым, а не готовой подписью: у закрытой кампании
        # состав — это снапшот на её момент, и предупредить об этом должен
        # экран. Текст под UI собирает фронт (то же решение, что badgeLabel в 4e).
        "campaign_status": campaign.status,
        "students_count": len(rows_out),
        "assessments_total": total_all,
        "assessments_completed": completed_all,
        "coverage_percent": round(completed_all / total_all * 100, 1) if total_all else 0.0,
        # Средний балл класса — среднее ПО УЧЕНИКАМ, каждый весит одинаково
        # (та же логика, что в average_profiles): иначе ученик, про которого
        # ответили пятеро, перевесил бы того, про кого ответил один.
        "class_average": round(sum(averages) / len(averages), 3) if averages else None,
        "average_delta": round(sum(deltas) / len(deltas), 3) if deltas else None,
        "students": rows_out,
    }
