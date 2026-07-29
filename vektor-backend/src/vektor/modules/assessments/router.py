# HTTP-слой assessments. Роутер тонкий: валидация схемой, вызов сервиса,
# маппинг доменных исключений в HTTP. Логики тут нет.

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
        db,
        data.title,
        data.period,
        data.opens_at,
        data.closes_at
    )
    return campaign


@router.post("/{campaign_id}/generate", response_model=GenerateResult)
async def generate_assessments(
    campaign_id: int,
    data: GenerateIn,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> GenerateResult:
    # TODO: вызвать service.generate_assessments(db, campaign_id, data.class_ids).
    #   Он возвращает кортеж (campaign, created) — распакуй и собери
    #   GenerateResult(created=created, campaign=campaign).
    #   Оберни в try/except service.CampaignNotFound → HTTPException 404.
    ...
