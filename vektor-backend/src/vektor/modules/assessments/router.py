from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.assessments import service
from vektor.modules.assessments.schemas import (
    CampaignCreate,
    CampaignOut,
    GenerateIn,
    GenerateResult,
)
from vektor.modules.auth.dependencies import require_role
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/campaigns", tags=["assessments"])


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
