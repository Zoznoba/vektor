from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.assessments import service
from vektor.modules.assessments.schemas import (
    AssessmentDetailOut,
    AssessmentListItemOut,
    CampaignCreate,
    CampaignDeleteResult,
    CampaignListItemOut,
    CampaignOut,
    GenerateIn,
    GenerateResult,
    SubmitAnswersIn,
    SubmitResult,
)
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/campaigns", tags=["assessments"])

# Отдельный роутер: прохождение анкет живёт под /assessments, а не /campaigns.
assessment_router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post(
    "",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать кампанию",
    description="Завести кампанию оценки в статусе `draft`. Анкеты появятся "
    "только после /campaigns/{id}/generate. Только админ.",
)
async def create_campaign(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignOut:
    campaign = await service.create_campaign(db, data.title, data.period_year, data.period_month)
    return campaign


@router.get(
    "",
    response_model=list[CampaignListItemOut],
    summary="Список кампаний",
    description="Все кампании школы с укрупнённым прогрессом (всего/заполнено "
    "анкет по кампании целиком). Разбивка по классам — отдельным эндпоинтом, "
    "/results/campaigns/{id}/coverage. Только админ.",
)
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> list[CampaignListItemOut]:
    return await service.list_campaigns(db)


@router.post(
    "/{campaign_id}/generate",
    response_model=GenerateResult,
    summary="Сгенерировать анкеты",
    description="Построить матрицу «кто кого оценивает» по указанным классам "
    "и кейсам и идемпотентно создать недостающие анкеты. Самооценка и "
    "родители — всегда; учителя — все учителя класса (кейса) либо только "
    "выбранные, если он указан в `teacher_ids_by_class` "
    "(`teacher_ids_by_case`): в школе ученика оценивают 2–4 учителя, а не "
    "весь педсостав; одноклассники — при `include_peers`. Нужен хотя бы один "
    "класс или кейс. Переводит кампанию в `active`. Только админ.",
)
async def generate_assessments(
    campaign_id: int,
    data: GenerateIn,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> GenerateResult:
    assessments = await service.generate_assessments(
        db,
        campaign_id,
        data.class_ids,
        data.include_peers,
        data.teacher_ids_by_class,
        data.case_ids,
        data.teacher_ids_by_case,
    )

    campaign, created = assessments
    return GenerateResult(created=created, campaign=campaign)


@router.patch(
    "/{campaign_id}/close",
    response_model=CampaignOut,
    summary="Закрыть кампанию",
    description="Перевести активную кампанию в `closed`: приём ответов прекращается. Только админ.",
)
async def close_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignOut:
    campaign = await service.close_campaign(db, campaign_id)

    return campaign


@router.patch(
    "/{campaign_id}/reopen",
    response_model=CampaignOut,
    summary="Возобновить кампанию",
    description="Перевести завершённую кампанию обратно в `active`: приём "
    "ответов снова открыт. Без дополнительных условий. Только админ.",
)
async def reopen_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignOut:
    campaign = await service.reopen_campaign(db, campaign_id)

    return campaign


@router.delete(
    "/{campaign_id}",
    response_model=CampaignDeleteResult,
    summary="Удалить кампанию",
    description="Удалить кампанию вместе со всеми её анкетами и ответами. "
    "Необратимо. Нужно, чтобы убирать тестовые и ошибочно заведённые "
    "кампании: «последний период» на экране результатов резолвится по дате "
    "кампании, и забытая пустая кампания скрывает настоящую диагностику. "
    "Только админ.",
)
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignDeleteResult:
    # Сервис возвращает dict — FastAPI собирает CampaignDeleteResult по
    # response_model. Исключения тут не ловим: CampaignNotFound — DomainError,
    # его разбирает общий обработчик из core/errors.py (Этап 7a).
    return await service.delete_campaign(db, campaign_id)


@assessment_router.get(
    "",
    response_model=list[AssessmentListItemOut],
    summary="Мои анкеты",
    description="Анкеты, где текущий пользователь — респондент (предстоит "
    "заполнить или уже заполнено), опционально отфильтрованные по кампании.",
)
async def list_assessments(
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AssessmentListItemOut]:
    return await service.list_my_assessments(db, user.id, campaign_id)


@assessment_router.get(
    "/{assessment_id}",
    response_model=AssessmentDetailOut,
    summary="Анкета для заполнения",
    description="Субъект и видимые для его возраста вопросы вместе с уже "
    "данными ответами. Видит только владелец анкеты (respondent_id).",
)
async def get_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssessmentDetailOut:
    assessment = await service.get_assessment_detail(db, assessment_id, user.id)

    return assessment


@assessment_router.post(
    "/{assessment_id}/answers",
    response_model=SubmitResult,
    summary="Сохранить ответы",
    description="Атомарный upsert пачки ответов в одной транзакции: "
    "видимость вопросов проверяется до записи, статус анкеты "
    "(`not_started`/`in_progress`/`completed`) пересчитывается по итогу.",
)
async def submit_answers(
    assessment_id: int,
    data: SubmitAnswersIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmitResult:
    result = await service.submit_answers(db, assessment_id, user.id, data.answers)

    return result
