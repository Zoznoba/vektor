# Бизнес-логика assessments. Права (только админ создаёт/генерит кампанию)
# проверяются в роутере через require_role(ADMIN) — здесь не дублируем.
#
# Срез 4b-1: создание кампании.
# Срез 4b-2 (следующий): generate_assessments — матрица «кто кого оценивает».


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.errors import DomainError
from vektor.modules.assessments.models import Answer, Assessment, Campaign
from vektor.modules.classes.models import SchoolClass
from vektor.modules.competencies.models import Question, QuestionnaireVersion
from vektor.modules.users.models import User
from vektor.shared.enums import AssessmentStatus, CampaignStatus, RaterRole


class CampaignNotFound(DomainError):
    """Кампания с таким id не найдена."""

    status_code = 404
    code = "campaign_not_found"
    message = "Кампания не найдена"


class AssessmentNotFound(DomainError):
    """Анкета с таким id не найдена."""

    status_code = 404
    code = "assessment_not_found"
    message = "Анкета не найдена"


class NotAssessmentOwner(DomainError):
    """Пользователь пытается открыть/заполнить не свою анкету."""

    status_code = 403
    code = "not_assessment_owner"
    message = "Пользователь не является владельцем анкеты"


class CampaignNotClosed(DomainError):
    """Возобновить можно только завершённую кампанию."""

    status_code = 409
    code = "campaign_not_closed"
    message = "Возобновить можно только завершённую кампанию"


class CampaignNotActive(DomainError):
    """Кампания не в статусе active.

    Сообщение переопределяется в точке возбуждения: для приёма ответов это
    «прием закрыт», для закрытия кампании — «закрыть можно только активную».
    """

    status_code = 409
    code = "campaign_not_active"
    message = "Кампания не активна"


class QuestionNotAllowed(DomainError):
    """Ответ на вопрос, которого нет в видимом наборе этой анкеты."""

    status_code = 422
    code = "question_not_allowed"
    message = "Ответ на недоступный вопрос"


class NoCurrentQuestionnaireVersion(DomainError):
    """Ни одна редакция анкеты не помечена действующей — не по чему создавать
    кампанию. В норме недостижимо: миграция c3f81ad0e7b5 ставит флаг, а
    частичный уникальный индекс не даёт завести вторую действующую.

    Раньше это исключение не ловил никто, и вместо осмысленного ответа клиент
    получал 500 — ровно тот случай, ради которого заведён общий обработчик.
    """

    status_code = 409
    code = "no_current_questionnaire_version"
    message = "Нет действующей редакции анкеты"


async def create_campaign(
    db: AsyncSession,
    title: str,
    period_year: int,
    period_month: int,
) -> Campaign:
    # Новая кампания всегда идёт по ДЕЙСТВУЮЩЕЙ редакции анкеты. Архивные
    # редакции сюда не попадают никогда — их назначает только импорт.
    current_version = await db.execute(
        select(QuestionnaireVersion.id).where(QuestionnaireVersion.is_current.is_(True))
    )
    version_id = current_version.scalar_one_or_none()
    if version_id is None:
        raise NoCurrentQuestionnaireVersion()

    campaign = Campaign(
        title=title,
        period_year=period_year,
        period_month=period_month,
        questionnaire_version_id=version_id,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def list_campaigns(db: AsyncSession) -> list[dict]:
    """Все кампании школы с укрупнённым прогрессом — под админский экран
    «Кампании 360°» (список карточек сверху).

    Прогресс — агрегат по ВСЕЙ кампании (total/completed анкет), не по
    классам: разбивка по классам уже есть отдельно в
    results.get_campaign_coverage, дублировать её здесь незачем. Одним
    запросом на подсчёт, а не N+1 на кампанию — кампаний немного, но
    привычка та же, что и у coverage.
    """
    campaigns = (
        (await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))).scalars().all()
    )

    completed = func.count().filter(Assessment.status == AssessmentStatus.COMPLETED)
    count_rows = await db.execute(
        select(
            Assessment.campaign_id, func.count().label("total"), completed.label("completed")
        ).group_by(Assessment.campaign_id)
    )
    counts = {row.campaign_id: (row.total, row.completed) for row in count_rows}

    return [
        {
            "id": c.id,
            "title": c.title,
            "period_year": c.period_year,
            "period_month": c.period_month,
            "status": c.status,
            "created_at": c.created_at,
            "total_assessments": counts.get(c.id, (0, 0))[0],
            "completed_assessments": counts.get(c.id, (0, 0))[1],
        }
        for c in campaigns
    ]


async def close_campaign(db: AsyncSession, campaign_id: int) -> Campaign:
    """Закрыть кампанию: active → closed. Только из active — черновик (draft)
    закрывать нечего (анкеты ещё не сгенерированы), а уже закрытую второй раз
    закрывать бессмысленно.

    Нужно, чтобы кампанию вообще можно было завершить через API: результаты и
    динамика считаются по завершённым периодам, а до этого статус closed
    появлялся только из импорта/дампа.
    """

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise CampaignNotFound()
    if campaign.status != CampaignStatus.ACTIVE:
        raise CampaignNotActive("Закрыть можно только активную кампанию")

    campaign.status = CampaignStatus.CLOSED
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def reopen_campaign(db: AsyncSession, campaign_id: int) -> Campaign:
    """Возобновить кампанию: closed → active. Симметрично close_campaign,
    без дополнительных условий — админ сам решает, когда это уместно (см.
    обсуждение при добавлении: единственное место, реально завязанное на
    статус, — submit_answers, а results/dynamics считают предыдущий период
    по периоду кампании, не по статусу, так что переоткрытие ничего не рвёт).
    """

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise CampaignNotFound()
    if campaign.status != CampaignStatus.CLOSED:
        raise CampaignNotClosed()

    campaign.status = CampaignStatus.ACTIVE
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def delete_campaign(db: AsyncSession, campaign_id: int) -> dict:
    """Удалить кампанию вместе со всеми её анкетами и ответами. Необратимо.

    Зачем вообще: единственный способ убрать кампанию до сих пор был SQL
    руками, и дважды (находки 7g и сегодняшняя) забытая тестовая кампания
    молча перебивала боевую в резолюции «последний период» — экран
    результатов у всех учеников школы становился пустым.

    ВАЖНО про порядок удаления: каскада на уровне БД у нас НЕТ. У
    Assessment.answers каскад только ORM-ный (delete-orphan) и срабатывает
    лишь для объектов, реально загруженных в сессию, — bulk-DELETE его не
    запускает. Значит, чистим руками и снизу вверх: answers → assessments →
    campaign. В обратном порядке FK-констрейнт даст IntegrityError.

    Всё — в ОДНОЙ транзакции (один commit в конце): частично снесённая
    кампания — это осиротевшие ответы, которые уже ничем не найти.

    TODO(Максим):
      1. campaign = await db.get(Campaign, campaign_id); нет → raise CampaignNotFound()
      2. Подзапрос с id анкет кампании:
             assessment_ids = select(Assessment.id).where(Assessment.campaign_id == campaign_id)
         Отдельным select'ом СНАЧАЛА посчитай, сколько ответов и анкет
         удалится — после DELETE считать будет уже нечего, а числа нужны
         в ответе (CampaignDeleteResult).
      3. Удаление — bulk-DELETE, а не «загрузить объекты и db.delete(...)»:
         анкет в кампании бывает под 400, грузить их в сессию незачем.
             from sqlalchemy import delete  # добавь в импорты сверху
             await db.execute(delete(Answer).where(Answer.assessment_id.in_(assessment_ids)))
             await db.execute(delete(Assessment).where(Assessment.campaign_id == campaign_id))
             await db.delete(campaign)   # он уже в сессии, отдельный DELETE не нужен
      4. await db.commit()
      5. Верни dict под CampaignDeleteResult:
             {"campaign_id": ..., "assessments_deleted": ..., "answers_deleted": ...}

    Вопрос, который надо решить тебе (я бы ответил «нет»): резать ли
    удаление активной кампании (status == active)? Аргумент «за» — защита от
    сноса идущего сбора. Аргумент «против» — мусорные кампании как раз
    бывают в любом статусе, а подтверждение с числами уже показывает UI.
    Если решишь резать — заведи отдельный DomainError на 409, не переиспользуй
    CampaignNotActive (у него противоположный смысл).
    """
    raise NotImplementedError


# Приоритет ролей при коллизии: один человек может быть и родителем ученика,
# и учителем его класса. Роль должна быть ОДНА и выбираться детерминированно,
# иначе она зависела бы от порядка циклов ниже.
_RATER_ROLE_PRIORITY = {
    RaterRole.SELF: 0,
    RaterRole.TEACHER: 1,
    RaterRole.PARENT: 2,
    RaterRole.PEER: 3,
}


def build_pairs(
    student_ids: list[int],
    parent_ids_by_student: dict[int, list[int]],
    teacher_ids: list[int],
    include_peers: bool = False,
) -> dict[tuple[int, int], RaterRole]:
    """Чистое доменное ядро: строит пары (respondent_id, subject_id) → роль
    для ОДНОГО класса. Без БД — юнит-тестируется на голых числах.

    Правила (субъект всегда student):
      • самооценка:    (s, s)                 ВСЕГДА, для каждого ученика s
      • родители:      (parent, s)            для каждого родителя ученика s
      • учителя:       (teacher, s)           для каждого учителя класса
      • одноклассники: (other, s)             ТОЛЬКО если include_peers=True

    Возвращаем dict, а не set: роль оценивающего нужна дальше — она
    сохраняется в Assessment.rater_role и потом читается результатами
    (Этап 5) вместо пересчёта по текущим связям. Дубли схлопываются по
    ключу, при коллизии ролей выигрывает более специфичная
    (_RATER_ROLE_PRIORITY). Вызывающий код объединяет несколько классов
    через merge_pairs.
    """
    pairs: dict[tuple[int, int], RaterRole] = {}

    def put(respondent: int, subject: int, role: RaterRole) -> None:
        current = pairs.get((respondent, subject))
        if current is None or _RATER_ROLE_PRIORITY[role] < _RATER_ROLE_PRIORITY[current]:
            pairs[(respondent, subject)] = role

    for s in student_ids:
        put(s, s, RaterRole.SELF)
        for p in parent_ids_by_student.get(s, []):
            put(p, s, RaterRole.PARENT)
        for t in teacher_ids:
            put(t, s, RaterRole.TEACHER)

    if include_peers:
        for i, r in enumerate(student_ids):
            for s in student_ids[i + 1 :]:
                put(r, s, RaterRole.PEER)
                put(s, r, RaterRole.PEER)

    return pairs


def merge_pairs(
    target: dict[tuple[int, int], RaterRole],
    extra: dict[tuple[int, int], RaterRole],
) -> None:
    """Влить пары одного класса в общий свод, уважая приоритет ролей.

    Простой `target |= extra` не годится: один и тот же человек может быть
    учителем в одном классе кампании и родителем ученика в другом — при
    слепом обновлении роль зависела бы от порядка обхода классов.
    """
    for pair, role in extra.items():
        current = target.get(pair)
        if current is None or _RATER_ROLE_PRIORITY[role] < _RATER_ROLE_PRIORITY[current]:
            target[pair] = role


def _teachers_for_class(
    cls: SchoolClass, teacher_ids_by_class: dict[int, list[int]] | None
) -> list[int]:
    """Учителя класса, участвующие в кампании.

    Выбор пересекается с фактическим составом класса, а не берётся на веру:
    иначе в кампанию попал бы учитель, которого успели открепить между
    открытием экрана и генерацией — с ролью TEACHER и доступом к результатам
    чужого класса. Ошибку при этом не поднимаем: генерация идемпотентна и
    запускается повторно, а «молча пропустить открепившегося» здесь честнее,
    чем свалить весь запуск из-за одной устаревшей галочки.
    """
    all_ids = [t.id for t in cls.teachers]
    if teacher_ids_by_class is None or cls.id not in teacher_ids_by_class:
        return all_ids
    chosen = set(teacher_ids_by_class[cls.id])
    return [tid for tid in all_ids if tid in chosen]


async def generate_assessments(
    db: AsyncSession,
    campaign_id: int,
    class_ids: list[int],
    include_peers: bool = False,
    teacher_ids_by_class: dict[int, list[int]] | None = None,
) -> tuple[Campaign, int]:
    """Оркестрация: грузит классы из БД, строит матрицу через build_pairs,
    идемпотентно вставляет НОВЫЕ анкеты, переводит кампанию в ACTIVE.
    Возвращает (campaign, сколько_новых_создано).

    `teacher_ids_by_class` — какие учителя класса участвуют в оценке. Так
    работает диагностика в школе: ученика оценивают не все 11 предметников, а
    выбранные администратором 2–4. Отсутствие класса в словаре означает «все
    учителя класса» — на этом стоят кампании, созданные до появления выбора.
    Пустой список — сознательное «учительских анкет по классу не делать»,
    поэтому он НЕ приравнивается к отсутствию ключа.

    Верхней границы на число учителей нет намеренно: 2–4 — это практика, а не
    инвариант данных, и упереться в неё школа может по своим причинам.
    Предупреждает UI, запрещать нечего.
    """

    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise CampaignNotFound()

    classes_sample = await db.execute(
        select(SchoolClass)
        .where(SchoolClass.id.in_(class_ids))
        .options(
            selectinload(SchoolClass.students).selectinload(User.parents),
            selectinload(SchoolClass.teachers),
        )
    )

    all_pairs: dict[tuple[int, int], RaterRole] = {}
    # Класс субъекта на момент генерации — снапшот, см. Assessment.subject_class_id.
    # Собираем здесь, в оркестрации, а не в build_pairs: та остаётся чистой
    # функцией на голых числах, класс ей для матрицы «кто кого» не нужен.
    # Коллизий нет: у ученика ровно один класс (FK), в двух классах кампании
    # он оказаться не может.
    class_id_by_subject: dict[int, int] = {}

    for cls in classes_sample.scalars():
        student_ids = [s.id for s in cls.students]
        parent_ids_by_student = {s.id: [p.id for p in s.parents] for s in cls.students}
        teacher_ids = _teachers_for_class(cls, teacher_ids_by_class)

        class_id_by_subject.update({s.id: cls.id for s in cls.students})

        merge_pairs(
            all_pairs,
            build_pairs(student_ids, parent_ids_by_student, teacher_ids, include_peers),
        )

    existing_pairs = await db.execute(
        select(Assessment.respondent_id, Assessment.subject_id).where(
            Assessment.campaign_id == campaign_id
        )
    )

    already_generated = set(existing_pairs.all())
    new_pairs = {pair: role for pair, role in all_pairs.items() if pair not in already_generated}
    db.add_all(
        [
            Assessment(
                campaign_id=campaign_id,
                respondent_id=r,
                subject_id=s,
                rater_role=role,
                subject_class_id=class_id_by_subject.get(s),
            )
            for (r, s), role in new_pairs.items()
        ]
    )

    campaign.status = CampaignStatus.ACTIVE
    await db.commit()
    await db.refresh(campaign)

    return campaign, len(new_pairs)


def is_question_visible(
    min_grade: int | None, max_grade: int | None, subject_grade: int | None
) -> bool:
    """Чистое доменное правило: показывать ли вопрос в анкете про субъекта.

    Возраст — свойство КРИТЕРИЯ, а не вопроса: границы приходят из
    Competency.min_grade/max_grade, поэтому критерий либо показывается целиком
    (все три вопроса), либо не показывается вовсе. Раньше признак жил на
    вопросе (is_conditional), и критерий мог посчитаться по неполному набору —
    средний балл прыгал при переходе из класса в класс сам по себе.

    Границы не заданы — вопрос виден всегда. Если границы есть, а класс
    субъекта неизвестен (None) — прячем: не раскрыть лишнего безопаснее.
    Юнит-тестируется без БД.
    """
    if min_grade is None and max_grade is None:
        return True
    if subject_grade is None:
        return False
    if min_grade is not None and subject_grade < min_grade:
        return False
    return max_grade is None or subject_grade <= max_grade


async def get_visible_questions_for_assessment(
    db: AsyncSession, assessment: Assessment
) -> list[Question]:
    """Все вопросы (упорядоченные по competency_id, order), видимые в этой
    анкете — с учётом класса субъекта (is_question_visible).

    Набор вопросов ограничен РЕДАКЦИЕЙ анкеты этой кампании. Без этого
    фильтра выборка склеила бы все редакции сразу: после появления архивной
    редакции (миграция c3f81ad0e7b5) действующая кампания начала бы отдавать
    66 вопросов вместо 33.

    Класс берём из СНАПШОТА assessment.subject_class, а не из текущего
    User.school_class: иначе перевод ученика в 9-й класс задним числом
    открывал бы условные вопросы в прошлогодних анкетах (см. комментарий у
    Assessment.subject_class_id). Требует selectinload на subject_class и
    campaign у вызывающего.
    """
    subject_grade = assessment.subject_class.grade if assessment.subject_class else None

    # Возрастные границы лежат на компетенции, поэтому её грузим сразу:
    # без selectinload обращение к q.competency в фильтре ниже дало бы
    # MissingGreenlet (ленивая подгрузка внутри async-контекста).
    q_ordered_questions = await db.execute(
        select(Question)
        .where(Question.version_id == assessment.campaign.questionnaire_version_id)
        .options(selectinload(Question.competency))
        .order_by(Question.competency_id, Question.order)
    )
    return [
        q
        for q in q_ordered_questions.scalars()
        if is_question_visible(q.competency.min_grade, q.competency.max_grade, subject_grade)
    ]


async def get_assessment_detail(db: AsyncSession, assessment_id: int, current_user_id: int) -> dict:
    """Собрать анкету для прохождения: субъект + видимые вопросы с уже данными
    ответами. Видит только сам респондент (владелец анкеты)."""

    q_assessment = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.campaign),
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.subject_class),
            selectinload(Assessment.answers),
        )
    )
    assessment = q_assessment.scalar_one_or_none()
    if assessment is None:
        raise AssessmentNotFound()

    if assessment.respondent_id != current_user_id:
        raise NotAssessmentOwner()

    visible_questions = await get_visible_questions_for_assessment(db, assessment)
    already_answered = {answer.question_id: answer.value for answer in assessment.answers}

    questions = [
        {
            "id": q.id,
            "competency_id": q.competency_id,
            "text": q.text,
            "order": q.order,
            # Контракт наружу не меняем: фронту по-прежнему нужен признак
            # «вопрос показывается не всем», просто источник теперь критерий.
            "is_conditional": q.competency.min_grade is not None
            or q.competency.max_grade is not None,
            "value": already_answered.get(q.id),
        }
        for q in visible_questions
    ]

    return {
        "id": assessment.id,
        "campaign_id": assessment.campaign_id,
        "campaign_title": assessment.campaign.title,
        "subject": assessment.subject,
        "rater_role": assessment.rater_role,
        "questions": questions,
    }


def compute_status(answered_questions: int, total_questions: int) -> AssessmentStatus:
    """Чистое правило статуса анкеты по прогрессу. Юнит-тестируется без БД.

    0 отвеченных → not_started; всё видимое отвечено → completed;
    что-то посередине → in_progress. total_questions=0 (нет видимых вопросов)
    трактуем как completed — заполнять нечего.
    """
    if total_questions == 0 or answered_questions >= total_questions:
        return AssessmentStatus.COMPLETED
    if answered_questions == 0:
        return AssessmentStatus.NOT_STARTED
    return AssessmentStatus.IN_PROGRESS


async def list_my_assessments(
    db: AsyncSession, current_user_id: int, campaign_id: int | None = None
) -> list[dict]:
    """Все анкеты, где current_user — респондент (то, что ему предстоит/уже
    заполнено), опционально отфильтрованные по кампании. Прогресс считается
    так же, как в submit_answers — по видимым для субъекта вопросам."""

    query = (
        select(Assessment)
        .where(Assessment.respondent_id == current_user_id)
        .options(
            selectinload(Assessment.campaign),
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.subject_class),
            selectinload(Assessment.answers),
        )
    )
    if campaign_id is not None:
        query = query.where(Assessment.campaign_id == campaign_id)

    result = await db.execute(query)

    items = []
    for assessment in result.scalars():
        visible_questions = await get_visible_questions_for_assessment(db, assessment)
        visible_ids = {q.id for q in visible_questions}
        answered = {a.question_id for a in assessment.answers} & visible_ids
        items.append(
            {
                "id": assessment.id,
                "campaign_id": assessment.campaign_id,
                "campaign_title": assessment.campaign.title,
                "campaign_period_year": assessment.campaign.period_year,
                "campaign_period_month": assessment.campaign.period_month,
                "subject": assessment.subject,
                "is_self": assessment.respondent_id == assessment.subject_id,
                "rater_role": assessment.rater_role,
                "status": assessment.status,
                "answered_questions": len(answered),
                "total_questions": len(visible_ids),
            }
        )
    return items


async def submit_answers(
    db: AsyncSession, assessment_id: int, current_user_id: int, answers: list
) -> dict:
    """Атомарно сохранить пачку ответов (upsert) и пересчитать статус анкеты.
    answers — list[AnswerIn] (у каждого .question_id и .value).

    Всё в ОДНОЙ транзакции: любая проверка падает ДО commit → ничего не пишется.
    """

    assessment_query = await db.execute(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.campaign),
            selectinload(Assessment.subject).selectinload(User.school_class),
            selectinload(Assessment.subject_class),
            selectinload(Assessment.answers),
        )
    )
    assessment = assessment_query.scalar_one_or_none()
    if assessment is None:
        raise AssessmentNotFound()

    if assessment.respondent_id != current_user_id:
        raise NotAssessmentOwner()

    if assessment.campaign.status != CampaignStatus.ACTIVE:
        raise CampaignNotActive("Приём ответов закрыт")

    visible_questions = await get_visible_questions_for_assessment(db, assessment)
    visible_ids = {q.id for q in visible_questions}

    existing_answers = {a.question_id: a for a in assessment.answers}

    # Сначала валидация: все присланные question_id должны быть в видимом наборе
    for incoming_answer in answers:
        if incoming_answer.question_id not in visible_ids:
            raise QuestionNotAllowed()

    # Затем апдейт/инсерт, чтобы не было частичного сохранения (транзакция откатится при ошибке)
    for incoming_answer in answers:
        if incoming_answer.question_id in existing_answers:
            existing_answers[incoming_answer.question_id].value = incoming_answer.value
        else:
            new_answer = Answer(
                assessment_id=assessment_id,
                question_id=incoming_answer.question_id,
                value=incoming_answer.value,
            )
            db.add(new_answer)

    answered_qids = set(existing_answers.keys()) | {i.question_id for i in answers}
    answered_questions_count = len(visible_ids & answered_qids)
    assessment.status = compute_status(answered_questions_count, len(visible_ids))

    await db.commit()
    return {
        "assessment_id": assessment.id,
        "status": assessment.status,
        "answered_questions": answered_questions_count,
        "total_questions": len(visible_ids),
    }
