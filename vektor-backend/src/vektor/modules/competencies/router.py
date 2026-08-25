from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.competencies import service
from vektor.modules.competencies.schemas import (
    ArchiveIn,
    BuilderCompetencyOut,
    BuilderOutcomeAreaOut,
    BuilderQuestionOut,
    CompetencyIn,
    CompetencyOut,
    MoveIn,
    OutcomeAreaIn,
    QuestionIn,
    QuestionnaireTreeOut,
    QuestionnaireVersionOut,
)
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/competencies", tags=["competencies"])

# Конструктор анкеты (Этап 7): черновик редакции + CRUD глав/критериев/
# вопросов. builder_router — всё, что привязано к конкретной версии
# (/questionnaire-versions/...); items_router — точечные правки уже
# созданных строк по их собственному id (/outcome-areas/{id}, /questions/{id}),
# БЕЗ префикса /questionnaire-versions — иначе он приклеился бы и сюда.
builder_router = APIRouter(prefix="/questionnaire-versions", tags=["competencies"])
items_router = APIRouter(tags=["competencies"])


def _area_out(area) -> BuilderOutcomeAreaOut:
    """CRUD-мутации не догружают .competencies (иначе ленивая подгрузка в
    async-контексте упала бы MissingGreenlet) — сериализуем явно, без неё."""
    return BuilderOutcomeAreaOut(
        id=area.id,
        name=area.name,
        order=area.order,
        is_archived=area.is_archived,
        is_draft=area.is_draft,
        competencies=[],
    )


def _competency_out(competency) -> BuilderCompetencyOut:
    return BuilderCompetencyOut(
        id=competency.id,
        name=competency.name,
        description=competency.description,
        order=competency.order,
        min_grade=competency.min_grade,
        max_grade=competency.max_grade,
        is_archived=competency.is_archived,
        is_draft=competency.is_draft,
        questions=[],
    )


@router.get(
    "",
    response_model=list[CompetencyOut],
    summary="Справочник критериев",
    description="11 критериев (по 3 вопроса), сгруппированных в 5 «ОР / навык», "
    "с возрастными границами и текущей редакцией вопросов.",
)
async def list_competencies(
    db: AsyncSession = Depends(get_db), _login_user: User = Depends(get_current_user)
) -> list[CompetencyOut]:
    return await service.list_competencies(db)


@builder_router.get(
    "",
    response_model=list[QuestionnaireVersionOut],
    summary="Список редакций анкеты",
    description="Все редакции (published и черновик, если есть), новые сверху. Только админ.",
)
async def list_versions(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> list[QuestionnaireVersionOut]:
    return await service.list_versions(db)


@builder_router.post(
    "/draft",
    response_model=QuestionnaireVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать черновик анкеты",
    description="Клонировать действующую редакцию в черновик для редактирования. "
    "Одновременно может существовать только один черновик. Только админ.",
)
async def create_draft(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> QuestionnaireVersionOut:
    return await service.create_draft_version(db)


@builder_router.get(
    "/{version_id}/tree",
    response_model=QuestionnaireTreeOut,
    summary="Дерево анкеты для конструктора",
    description="Главы → критерии → вопросы указанной редакции, включая архивные "
    "и ещё не опубликованные (is_archived/is_draft). Только админ.",
)
async def get_tree(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> QuestionnaireTreeOut:
    return await service.get_tree(db, version_id)


@builder_router.post(
    "/{version_id}/publish",
    response_model=QuestionnaireVersionOut,
    summary="Опубликовать черновик",
    description="Черновик становится действующей редакцией (is_current), старая "
    "остаётся в истории. Необратимо — назад в черновик не вернуть. Только админ.",
)
async def publish_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> QuestionnaireVersionOut:
    return await service.publish_version(db, version_id)


@builder_router.delete(
    "/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отменить черновик",
    description="Удалить черновик со всеми его вопросами и заведёнными в нём "
    "главами/критериями. Только админ.",
)
async def discard_draft(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    await service.discard_draft(db, version_id)


@builder_router.post(
    "/{version_id}/outcome-areas",
    response_model=BuilderOutcomeAreaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить «ОР / навык»",
    description="Только внутри черновика. Только админ.",
)
async def add_outcome_area(
    version_id: int,
    data: OutcomeAreaIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderOutcomeAreaOut:
    area = await service.add_outcome_area(db, version_id, data.name)
    return _area_out(area)


@items_router.patch(
    "/outcome-areas/{area_id}",
    response_model=BuilderOutcomeAreaOut,
    summary="Переименовать «ОР / навык»",
    description="Применяется сразу, независимо от черновика — это правка формулировки, "
    "а не структуры. Только админ.",
)
async def update_outcome_area(
    area_id: int,
    data: OutcomeAreaIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderOutcomeAreaOut:
    area = await service.update_outcome_area(db, area_id, data.name)
    return _area_out(area)


@items_router.patch(
    "/outcome-areas/{area_id}/archive",
    response_model=BuilderOutcomeAreaOut,
    summary="Архивировать/восстановить «ОР / навык»",
    description="Архивная область скрыта из новых черновиков, но её критерии и "
    "прошлые результаты по ней никуда не деваются. Только админ.",
)
async def archive_outcome_area(
    area_id: int,
    data: ArchiveIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderOutcomeAreaOut:
    area = await service.set_outcome_area_archived(db, area_id, data.is_archived)
    return _area_out(area)


@items_router.patch(
    "/outcome-areas/{area_id}/move",
    response_model=BuilderOutcomeAreaOut,
    summary="Передвинуть «ОР / навык»",
    description="Поменять местами с соседом по порядку (up/down). Только админ.",
)
async def move_outcome_area(
    area_id: int,
    data: MoveIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderOutcomeAreaOut:
    area = await service.move_outcome_area(db, area_id, data.direction)
    return _area_out(area)


@builder_router.post(
    "/{version_id}/outcome-areas/{area_id}/competencies",
    response_model=BuilderCompetencyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить критерий",
    description="Только внутри черновика. Только админ.",
)
async def add_competency(
    version_id: int,
    area_id: int,
    data: CompetencyIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderCompetencyOut:
    competency = await service.add_competency(
        db, version_id, area_id, data.name, data.description, data.min_grade, data.max_grade
    )
    return _competency_out(competency)


@items_router.patch(
    "/competencies/{competency_id}",
    response_model=BuilderCompetencyOut,
    summary="Изменить критерий",
    description="Название, описание и возрастные границы. Применяется сразу, "
    "независимо от черновика. Только админ.",
)
async def update_competency(
    competency_id: int,
    data: CompetencyIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderCompetencyOut:
    competency = await service.update_competency(
        db, competency_id, data.name, data.description, data.min_grade, data.max_grade
    )
    return _competency_out(competency)


@items_router.patch(
    "/competencies/{competency_id}/archive",
    response_model=BuilderCompetencyOut,
    summary="Архивировать/восстановить критерий",
    description="Архивный критерий скрыт из новых черновиков, прошлая аналитика "
    "по нему не меняется. Только админ.",
)
async def archive_competency(
    competency_id: int,
    data: ArchiveIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderCompetencyOut:
    competency = await service.set_competency_archived(db, competency_id, data.is_archived)
    return _competency_out(competency)


@items_router.patch(
    "/competencies/{competency_id}/move",
    response_model=BuilderCompetencyOut,
    summary="Передвинуть критерий",
    description="Поменять местами с соседом внутри своей главы (up/down). Только админ.",
)
async def move_competency(
    competency_id: int,
    data: MoveIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderCompetencyOut:
    competency = await service.move_competency(db, competency_id, data.direction)
    return _competency_out(competency)


@builder_router.post(
    "/{version_id}/competencies/{competency_id}/questions",
    response_model=BuilderQuestionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить вопрос",
    description="Только внутри черновика. Только админ.",
)
async def add_question(
    version_id: int,
    competency_id: int,
    data: QuestionIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderQuestionOut:
    return await service.add_question(db, version_id, competency_id, data.text)


@items_router.patch(
    "/questions/{question_id}",
    response_model=BuilderQuestionOut,
    summary="Изменить текст вопроса",
    description="Только админ.",
)
async def update_question(
    question_id: int,
    data: QuestionIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderQuestionOut:
    return await service.update_question(db, question_id, data.text)


@items_router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить вопрос",
    description="Только внутри черновика — у опубликованной редакции вопросы "
    "уже могут быть отвечены и удалению не подлежат. Только админ.",
)
async def delete_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    await service.delete_question(db, question_id)


@items_router.patch(
    "/questions/{question_id}/move",
    response_model=BuilderQuestionOut,
    summary="Передвинуть вопрос",
    description="Поменять местами с соседом внутри своего критерия (up/down). Только админ.",
)
async def move_question(
    question_id: int,
    data: MoveIn,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BuilderQuestionOut:
    return await service.move_question(db, question_id, data.direction)
