"""Оркестрация результатов: права + сборка ответа эндпоинта.

Модуль разложен на три файла (Этап 5 разросся до полутора тысяч строк):
domain.py — чистые правила без БД, repository.py — запросы, service.py —
то, что связывает их вместе и решает, кому что показывать.

Права считаются по ТЕКУЩИМ связям (доступ определяется тем, кто учитель и
родитель сейчас), а роли оценивающих в агрегации берутся зафиксированные
при генерации — см. repository.load_scored_answers.
"""

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
from vektor.modules.results.errors import NotAllowedToViewResults, SubjectNotFound
from vektor.modules.users.models import User
from vektor.shared.class_label import class_label
from vektor.shared.enums import RaterRole


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
    db: AsyncSession, class_id: int, only_completed: bool = True
) -> int | None:
    """Последняя кампания класса. Обёртка над общей репозиторной функцией:
    класс и кейс отличаются только колонкой снапшота."""
    return await repo.latest_campaign_id_for_group(
        db, Assessment.subject_class_id, class_id, only_completed
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


async def _group_profile(
    db: AsyncSession,
    campaign_id: int,
    snapshot_column,
    group_id: int,
    score_key: str,
) -> dict:
    """Общее ядро профиля группы: класс и кейс считаются ОДИНАКОВО.

    Различий ровно три, и все три — параметры: колонка снапшота, id группы и
    префикс ключей в ответе (`class_avg` / `case_avg`). Всё остальное —
    состав по снапшоту, «школа» за период, среднее по ученикам, обе метрики
    под радаром — одно и то же, и раздваивать это нельзя: разъехавшись, две копии
    дали бы двум экранам разные числа по одним данным.

    Права и загрузка самой группы остаются у вызывающего: они у класса и
    кейса разные (SchoolClass против Case), и подмешивать их сюда значило бы
    протащить сюда же оба модуля.
    """
    campaign = await repo.load_completed_campaign(db, campaign_id)

    group_map = await repo.subject_group_map(db, campaign_id, snapshot_column)
    subject_ids = {sid for sid, gid in group_map.items() if gid == group_id}

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
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
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
    """Средний профиль класса, сравнение со школой и зоны роста класса."""
    school_class = await repo.load_class_with_teachers(db, class_id)
    if school_class is None:
        raise ClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    profile = await _group_profile(
        db, campaign_id, Assessment.subject_class_id, class_id, "class_avg"
    )
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

    profile = await _group_profile(db, campaign_id, Assessment.subject_case_id, case_id, "case_avg")
    return {
        "case_id": case_id,
        "case_name": case.name,
        "case_average": profile.pop("average"),
        **profile,
    }


async def _group_dynamics(
    db: AsyncSession,
    campaign_id: int,
    snapshot_column,
    group_id: int,
) -> dict:
    """Динамика группы по критериям: текущий период против предыдущего.

    Общее ядро для класса и кейса — как и `_group_profile`, различается
    только колонкой снапшота и id группы.

    Два правила, без которых сравнение врёт:

    1. **Сравниваем ОДНИХ И ТЕХ ЖЕ учеников.** Предыдущая кампания ищется по
       СУБЪЕКТУ (`previous_campaign_by_subject`), а не по группе: нынешний
       8-1 в прошлом году был 7-1, и поиск по id класса не нашёл бы ничего.
       В обе средние идут только те, у кого есть оба периода, — иначе
       пришедший в этом году новичок сдвигал бы «текущее» и разница читалась
       бы как рост коллектива.

    2. **Дельты только по общему ядру критериев.** Состав меняется
       (профпробы открываются с 9 класса), и появившийся критерий показываем
       со значением, но без дельты — иначе смена состава анкеты прочиталась
       бы как прирост.
    """
    campaign = await repo.load_completed_campaign(db, campaign_id)

    group_map = await repo.subject_group_map(db, campaign_id, snapshot_column)
    subject_ids = {sid for sid, gid in group_map.items() if gid == group_id}

    previous_ids = await repo.previous_campaign_by_subject(
        db, subject_ids, campaign.period_year, campaign.period_month
    )
    profiles = await repo.profiles_by_campaign_and_subject(
        db, {campaign_id} | set(previous_ids.values())
    )

    # Пары «сейчас / тогда» по каждому ученику: обе половины должны быть
    # непустыми, иначе это не сравнение.
    current_profiles: list[dict[int, float]] = []
    previous_profiles: list[dict[int, float]] = []
    compared_previous_campaigns: set[int] = set()
    for subject_id in subject_ids:
        current = profiles.get((campaign_id, subject_id))
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
            for (cid, sid), profile in profiles.items()
            if cid == campaign_id and sid in subject_ids and profile.overall
        ]

    current_scores = average_profiles(current_profiles)
    previous_scores = average_profiles(previous_profiles)
    core = shared_competencies(current_scores, previous_scores)
    deltas = compute_deltas(current_scores, previous_scores, core)

    # Ярлык прошлого периода берём по САМОЙ СВЕЖЕЙ из прошлых кампаний: в
    # норме она у всех одна (класс диагностируют целиком), но у кейса
    # ученики из разных классов и прошлые кампании у них могут различаться.
    previous_campaign = None
    if compared_previous_campaigns:
        candidates = [await repo.get_campaign(db, cid) for cid in compared_previous_campaigns]
        previous_campaign = max(
            (c for c in candidates if c is not None),
            key=lambda c: (c.period_year, c.period_month, c.id),
            default=None,
        )

    # Оговорка о смене редакции — как в get_subject_dynamics: текст берём из
    # самой редакции, придумывать его здесь нельзя.
    versions_differ = bool(
        previous_campaign
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
        "campaign_id": campaign_id,
        "campaign_title": campaign.title,
        "campaign_period_year": campaign.period_year,
        "campaign_period_month": campaign.period_month,
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
    """Динамика класса по критериям. Права те же, что у профиля класса."""
    school_class = await repo.load_class_with_teachers(db, class_id)
    if school_class is None:
        raise ClassNotFound()
    if not can_view_group_results(
        current_user.id, current_user.role, {t.id for t in school_class.teachers}
    ):
        raise NotAllowedToViewResults()

    dynamics = await _group_dynamics(db, campaign_id, Assessment.subject_class_id, class_id)
    return {
        "class_id": class_id,
        "class_label": f"{school_class.grade}-{school_class.section}",
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

    dynamics = await _group_dynamics(db, campaign_id, Assessment.subject_case_id, case_id)
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


async def get_class_roster(
    db: AsyncSession, class_id: int, campaign_id: int, current_user: User
) -> dict:
    """Состав класса с прогрессом диагностики: строка на ученика (статус
    самооценки, собрано анкет, итоговый балл, динамика) плюс метрики шапки.

    Права те же, что у профиля класса: admin или учитель ЭТОГО класса.
    """
    campaign = await repo.get_campaign(db, campaign_id)
    if campaign is None:
        raise CampaignNotFound()

    school_class = await repo.load_class_with_roster(db, class_id)
    if school_class is None:
        raise ClassNotFound()

    teacher_ids = {t.id for t in school_class.teachers}
    if not can_view_group_results(current_user.id, current_user.role, teacher_ids):
        raise NotAllowedToViewResults()

    # Состав берём по СНАПШОТУ анкет кампании, а не по текущему списку класса:
    # на прошлогоднюю кампанию должны попасть те, кто учился тогда, включая
    # выбывших. Текущих учеников без анкет добавляем отдельно — учитель должен
    # видеть, что диагностика по ним не выдана.
    class_map = await repo.subject_group_map(db, campaign_id, Assessment.subject_class_id)
    subject_ids = {sid for sid, cid in class_map.items() if cid == class_id}
    subject_ids |= {student.id for student in school_class.students}

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
