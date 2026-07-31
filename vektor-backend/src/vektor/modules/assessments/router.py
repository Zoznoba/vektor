from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.assessments import service
from vektor.modules.assessments.schemas import (
    AssessmentDetailOut,
    CampaignCreate,
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


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignOut:
    campaign = await service.create_campaign(
        db, data.title, data.period, data.opens_at, data.closes_at
    )
    return campaign


@router.post("/{campaign_id}/generate", response_model=GenerateResult)
async def generate_assessments(
    campaign_id: int,
    data: GenerateIn,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> GenerateResult:
    try:
        assessments = await service.generate_assessments(
            db, campaign_id, data.class_ids, data.include_peers
        )
    except service.CampaignNotFound as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Компания не найдена id: {campaign_id}"
        ) from err

    campaign, created = assessments
    return GenerateResult(created=created, campaign=campaign)


@assessment_router.get("/{assessment_id}", response_model=AssessmentDetailOut)
async def get_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AssessmentDetailOut:
    try:
        assessment = await service.get_assessment_detail(
            db, assessment_id, user.id
        )
    except service.AssessmentNotFound as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Анкета не найдена"
        ) from err
    except service.NotAssessmentOwner as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь не является владельцем анкеты"
        ) from err

    return assessment


@assessment_router.post("/{assessment_id}/answers", response_model=SubmitResult)
async def submit_answers(
    assessment_id: int,
    data: SubmitAnswersIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmitResult:
    # TODO: вызвать service.submit_answers(db, assessment_id, user.id, data.answers)
    #   и вернуть результат. Маппинг исключений:
    #     AssessmentNotFound  → 404
    #     NotAssessmentOwner  → 403
    #     CampaignNotActive   → 409 (приём закрыт)
    #     QuestionNotAllowed  → 422 (ответ на невидимый вопрос)
    ...
