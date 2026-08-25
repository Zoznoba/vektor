import secrets
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.core.errors import DomainError
from vektor.modules.competencies.models import (
    Competency,
    OutcomeArea,
    Question,
    QuestionnaireVersion,
)
from vektor.shared.enums import QuestionnaireVersionStatus


async def list_competencies(db: AsyncSession) -> Sequence[Competency]:
    # outcome_area догружаем явно: она уходит в CompetencyOut, а ленивая
    # подгрузка при сериализации в async-контексте даёт MissingGreenlet.
    # Архивные критерии сюда не попадают: это справочник ДЕЙСТВУЮЩЕЙ методики,
    # архивные остаются доступны только через builder-дерево и через
    # результаты прошлых кампаний (там строка не удаляется, см. is_archived).
    result = await db.execute(
        select(Competency)
        .where(Competency.is_archived.is_(False), Competency.is_draft.is_(False))
        .options(selectinload(Competency.questions), selectinload(Competency.outcome_area))
        .order_by(Competency.order)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Конструктор анкеты (Этап 7). См. models.py — OutcomeArea/Competency общие
# на все редакции (is_archived/is_draft), Question версионируется (version_id).
# ---------------------------------------------------------------------------


class VersionNotFound(DomainError):
    status_code = 404
    code = "questionnaire_version_not_found"
    message = "Редакция анкеты не найдена"


class VersionNotDraft(DomainError):
    """Структуру можно менять только в черновике — опубликованная редакция
    заморожена навсегда, иначе задним числом поехала бы историческая
    аналитика по кампаниям, которые её уже используют."""

    status_code = 409
    code = "questionnaire_version_not_draft"
    message = "Редактировать можно только черновик"


class DraftAlreadyExists(DomainError):
    """Одновременно редактируется не больше одного черновика — иначе
    is_draft на Competency/OutcomeArea не сказал бы, какому черновику
    принадлежит строка."""

    status_code = 409
    code = "draft_already_exists"
    message = "Черновик уже существует — опубликуйте или отмените его, прежде чем создавать новый"


class NoCurrentQuestionnaireVersion(DomainError):
    status_code = 409
    code = "no_current_questionnaire_version"
    message = "Нет действующей редакции анкеты"


class EmptyQuestionnaire(DomainError):
    status_code = 409
    code = "empty_questionnaire"
    message = "В черновике нет ни одного вопроса — публиковать нечего"


class OutcomeAreaNotFound(DomainError):
    status_code = 404
    code = "outcome_area_not_found"
    message = "«ОР / навык» не найдена"


class CompetencyNotFound(DomainError):
    status_code = 404
    code = "competency_not_found"
    message = "Критерий не найден"


class QuestionNotFound(DomainError):
    status_code = 404
    code = "question_not_found"
    message = "Вопрос не найден"


def _generate_code(prefix: str) -> str:
    """Случайный уникальный code для новых OutcomeArea/Competency/версий:
    это внутренний идентификатор, наружу в конструкторе не
    показывается (фронт всегда работает по id). Незнакомый code для старых
    потребителей (например, DynamicsChart) — штатный случай, они его уже
    умеют показывать через fallback на name."""
    return f"{prefix}-{secrets.token_hex(4)}"


async def list_versions(db: AsyncSession) -> Sequence[QuestionnaireVersion]:
    result = await db.execute(
        select(QuestionnaireVersion).order_by(QuestionnaireVersion.created_at.desc())
    )
    return result.scalars().all()


async def _require_draft(db: AsyncSession, version_id: int) -> QuestionnaireVersion:
    version = await db.get(QuestionnaireVersion, version_id)
    if version is None:
        raise VersionNotFound()
    if version.status != QuestionnaireVersionStatus.DRAFT:
        raise VersionNotDraft()
    return version


async def create_draft_version(db: AsyncSession) -> QuestionnaireVersion:
    """Завести черновик поверх действующей редакции: клонирует ТОЛЬКО вопросы
    (Question.version_id) — OutcomeArea/Competency общие, клонировать нечего.
    Дальше админ правит дерево через add_*/update_*/archive_*/move_*, пока не
    вызовет publish_version или discard_draft."""

    existing_draft = await db.scalar(
        select(QuestionnaireVersion).where(
            QuestionnaireVersion.status == QuestionnaireVersionStatus.DRAFT
        )
    )
    if existing_draft is not None:
        raise DraftAlreadyExists()

    current = await db.scalar(
        select(QuestionnaireVersion).where(QuestionnaireVersion.is_current.is_(True))
    )
    if current is None:
        raise NoCurrentQuestionnaireVersion()

    draft = QuestionnaireVersion(
        code=_generate_code("draft"),
        title=f"Черновик «{current.title}»",
        status=QuestionnaireVersionStatus.DRAFT,
        is_current=False,
    )
    db.add(draft)
    await db.flush()

    # Вопросы АРХИВНЫХ критериев в черновик не переносим: is_archived и
    # означает «скрыт из новых черновиков» (7l). В уже опубликованных
    # редакциях они остаются — прошлое неизменно, — но новая редакция
    # начинается без них, иначе архивирование не имело бы никакого эффекта
    # и критерий тянулся бы из редакции в редакцию вечно.
    source_questions = await db.execute(
        select(Question)
        .join(Competency, Competency.id == Question.competency_id)
        .where(Question.version_id == current.id, Competency.is_archived.is_(False))
    )
    for q in source_questions.scalars():
        db.add(
            Question(
                competency_id=q.competency_id,
                text=q.text,
                order=q.order,
                version_id=draft.id,
            )
        )

    await db.commit()
    await db.refresh(draft)
    return draft


async def discard_draft(db: AsyncSession, version_id: int) -> None:
    """Отменить черновик безвозвратно: вопросы этой версии и любые
    OutcomeArea/Competency, заведённые прямо в ней (is_draft), удаляются
    целиком — они никогда не были опубликованы и ни на что не ссылаются.
    Архивирование существующих критериев (is_archived) НЕ откатывается: это
    самостоятельное действие, не привязанное к жизни черновика."""

    version = await _require_draft(db, version_id)

    await db.execute(delete(Question).where(Question.version_id == version_id))
    await db.execute(delete(Competency).where(Competency.is_draft.is_(True)))
    await db.execute(delete(OutcomeArea).where(OutcomeArea.is_draft.is_(True)))
    await db.delete(version)
    await db.commit()


async def publish_version(db: AsyncSession, version_id: int) -> QuestionnaireVersion:
    """Опубликовать черновик: становится is_current, старая действующая
    редакция остаётся в БД как история (status published, is_current false —
    в точности как архивная 2025 сегодня). Новые OutcomeArea/Competency этого
    черновика перестают быть is_draft — с этого момента они полноправная
    часть общего справочника."""

    version = await _require_draft(db, version_id)

    question_count = await db.scalar(
        select(func.count()).select_from(Question).where(Question.version_id == version_id)
    )
    if not question_count:
        raise EmptyQuestionnaire()

    old_current = await db.scalar(
        select(QuestionnaireVersion).where(QuestionnaireVersion.is_current.is_(True))
    )
    if old_current is not None:
        old_current.is_current = False
        await db.flush()

    await db.execute(update(Competency).where(Competency.is_draft.is_(True)).values(is_draft=False))
    await db.execute(
        update(OutcomeArea).where(OutcomeArea.is_draft.is_(True)).values(is_draft=False)
    )

    version.status = QuestionnaireVersionStatus.PUBLISHED
    version.is_current = True
    await db.commit()
    await db.refresh(version)
    return version


async def get_tree(db: AsyncSession, version_id: int) -> dict:
    version = await db.get(QuestionnaireVersion, version_id)
    if version is None:
        raise VersionNotFound()

    areas_result = await db.execute(
        select(OutcomeArea)
        .options(selectinload(OutcomeArea.competencies).selectinload(Competency.questions))
        .order_by(OutcomeArea.order)
    )
    areas = areas_result.scalars().all()

    tree_areas = []
    for area in areas:
        tree_competencies = []
        for comp in sorted(area.competencies, key=lambda c: c.order):
            questions = sorted(
                (q for q in comp.questions if q.version_id == version_id),
                key=lambda q: q.order,
            )
            tree_competencies.append(
                {
                    "id": comp.id,
                    "name": comp.name,
                    "description": comp.description,
                    "order": comp.order,
                    "min_grade": comp.min_grade,
                    "max_grade": comp.max_grade,
                    "is_archived": comp.is_archived,
                    "is_draft": comp.is_draft,
                    "questions": questions,
                }
            )
        tree_areas.append(
            {
                "id": area.id,
                "name": area.name,
                "order": area.order,
                "is_archived": area.is_archived,
                "is_draft": area.is_draft,
                "competencies": tree_competencies,
            }
        )

    return {"version": version, "outcome_areas": tree_areas}


async def add_outcome_area(db: AsyncSession, version_id: int, name: str) -> OutcomeArea:
    await _require_draft(db, version_id)
    max_order = await db.scalar(select(func.max(OutcomeArea.order)))
    area = OutcomeArea(
        code=_generate_code("area"),
        name=name,
        order=(max_order + 1) if max_order is not None else 0,
        is_draft=True,
    )
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return area


async def update_outcome_area(db: AsyncSession, area_id: int, name: str) -> OutcomeArea:
    area = await db.get(OutcomeArea, area_id)
    if area is None:
        raise OutcomeAreaNotFound()
    area.name = name
    await db.commit()
    await db.refresh(area)
    return area


async def set_outcome_area_archived(
    db: AsyncSession, area_id: int, is_archived: bool
) -> OutcomeArea:
    area = await db.get(OutcomeArea, area_id)
    if area is None:
        raise OutcomeAreaNotFound()
    area.is_archived = is_archived
    await db.commit()
    await db.refresh(area)
    return area


async def _move(
    db: AsyncSession, model, item_id: int, direction: str, not_found, sibling_filter=None
):
    """Переставить item.order с соседом по direction — свободные места
    внутри одной группы (siblings), а не глобально. sibling_filter(item) →
    условие WHERE для группы; None — группа - вся таблица (у OutcomeArea
    группа одна на всех)."""
    item = await db.get(model, item_id)
    if item is None:
        raise not_found()

    query = select(model).order_by(model.order)
    if sibling_filter is not None:
        query = query.where(sibling_filter(item))
    siblings = (await db.execute(query)).scalars().all()

    index = next(i for i, s in enumerate(siblings) if s.id == item.id)
    neighbor_index = index - 1 if direction == "up" else index + 1
    if 0 <= neighbor_index < len(siblings):
        neighbor = siblings[neighbor_index]
        item.order, neighbor.order = neighbor.order, item.order
        await db.commit()
        await db.refresh(item)
    return item


async def move_outcome_area(db: AsyncSession, area_id: int, direction: str) -> OutcomeArea:
    return await _move(db, OutcomeArea, area_id, direction, OutcomeAreaNotFound)


async def add_competency(
    db: AsyncSession,
    version_id: int,
    area_id: int,
    name: str,
    description: str | None,
    min_grade: int | None,
    max_grade: int | None,
) -> Competency:
    await _require_draft(db, version_id)
    area = await db.get(OutcomeArea, area_id)
    if area is None:
        raise OutcomeAreaNotFound()

    max_order = await db.scalar(
        select(func.max(Competency.order)).where(Competency.outcome_area_id == area_id)
    )
    competency = Competency(
        code=_generate_code("comp"),
        name=name,
        description=description,
        order=(max_order + 1) if max_order is not None else 0,
        outcome_area_id=area_id,
        min_grade=min_grade,
        max_grade=max_grade,
        is_draft=True,
    )
    db.add(competency)
    await db.commit()
    await db.refresh(competency)
    return competency


async def update_competency(
    db: AsyncSession,
    competency_id: int,
    name: str,
    description: str | None,
    min_grade: int | None,
    max_grade: int | None,
) -> Competency:
    competency = await db.get(Competency, competency_id)
    if competency is None:
        raise CompetencyNotFound()
    competency.name = name
    competency.description = description
    competency.min_grade = min_grade
    competency.max_grade = max_grade
    await db.commit()
    await db.refresh(competency)
    return competency


async def set_competency_archived(
    db: AsyncSession, competency_id: int, is_archived: bool
) -> Competency:
    competency = await db.get(Competency, competency_id)
    if competency is None:
        raise CompetencyNotFound()
    competency.is_archived = is_archived
    await db.commit()
    await db.refresh(competency)
    return competency


async def move_competency(db: AsyncSession, competency_id: int, direction: str) -> Competency:
    return await _move(
        db,
        Competency,
        competency_id,
        direction,
        CompetencyNotFound,
        sibling_filter=lambda item: Competency.outcome_area_id == item.outcome_area_id,
    )


async def add_question(
    db: AsyncSession, version_id: int, competency_id: int, text: str
) -> Question:
    await _require_draft(db, version_id)
    competency = await db.get(Competency, competency_id)
    if competency is None:
        raise CompetencyNotFound()

    max_order = await db.scalar(
        select(func.max(Question.order)).where(
            Question.competency_id == competency_id, Question.version_id == version_id
        )
    )
    question = Question(
        competency_id=competency_id,
        text=text,
        order=(max_order + 1) if max_order is not None else 0,
        version_id=version_id,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


async def update_question(db: AsyncSession, question_id: int, text: str) -> Question:
    question = await db.get(Question, question_id)
    if question is None:
        raise QuestionNotFound()
    await _require_draft(db, question.version_id)
    question.text = text
    await db.commit()
    await db.refresh(question)
    return question


async def delete_question(db: AsyncSession, question_id: int) -> None:
    """Удаление разрешено только внутри черновика — у Question уже есть
    version_id, и вопрос опубликованной редакции физически используется в
    прошлых/активных Assessment.answers, удалять его нельзя ни при каких
    условиях (см. VersionNotDraft)."""
    question = await db.get(Question, question_id)
    if question is None:
        raise QuestionNotFound()
    await _require_draft(db, question.version_id)
    await db.delete(question)
    await db.commit()


async def move_question(db: AsyncSession, question_id: int, direction: str) -> Question:
    question = await db.get(Question, question_id)
    if question is None:
        raise QuestionNotFound()
    await _require_draft(db, question.version_id)
    return await _move(
        db,
        Question,
        question_id,
        direction,
        QuestionNotFound,
        sibling_filter=lambda item: (
            (Question.competency_id == item.competency_id)
            & (Question.version_id == item.version_id)
        ),
    )
