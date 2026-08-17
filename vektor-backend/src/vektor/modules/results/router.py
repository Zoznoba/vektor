from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.results import service
from vektor.modules.results.schemas import (
    CampaignCoverageOut,
    ClassResultsOut,
    DynamicsOut,
    ResultsOut,
    SubjectCampaignOut,
)
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/results", tags=["results"])

# ВНИМАНИЕ на порядок маршрутов: пути с литеральным первым сегментом
# (/class/..., /campaigns/...) объявлены ДО /{subject_id}. FastAPI разбирает
# маршруты в порядке объявления, и хотя конкретно эти по числу сегментов с
# /{subject_id} не пересекаются, держим литералы выше — так добавление
# следующего /{subject_id}/... не превратит /class/5 в «субъект по имени class».


@router.get("/class/{class_id}", response_model=ClassResultsOut)
async def get_class_results(
    class_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassResultsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_class(db, class_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У класса пока нет результатов",
            )
    return await service.get_class_results(db, class_id, campaign_id, user)


@router.get("/campaigns/{campaign_id}/coverage", response_model=CampaignCoverageOut)
async def get_campaign_coverage(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignCoverageOut:
    # Покрытие по всей школе — админский экран кампании, поэтому роль жёстко
    # ADMIN, а не «учитель своего класса», как у профиля класса.
    return await service.get_campaign_coverage(db, campaign_id)


@router.get("/{subject_id}", response_model=ResultsOut)
async def get_results(
    subject_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResultsOut:
    # campaign_id опционален: дашборд ученика показывает «мои результаты» и
    # про кампании не знает. Без него берём последнюю, где у субъекта есть
    # анкеты. Нет ни одной — 404, а не пустой ответ: «результатов ещё нет» и
    # «такого субъекта нет» фронт различает по detail.
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_subject(db, subject_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У пользователя пока нет результатов",
            )
    return await service.get_subject_results(db, subject_id, campaign_id, user)


@router.get("/{subject_id}/campaigns", response_model=list[SubjectCampaignOut])
async def list_subject_campaigns(
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubjectCampaignOut]:
    return await service.list_subject_campaigns(db, subject_id, user)


@router.get("/{subject_id}/dynamics", response_model=DynamicsOut)
async def get_dynamics(
    subject_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DynamicsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_subject(db, subject_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У пользователя пока нет результатов",
            )
    return await service.get_subject_dynamics(db, subject_id, campaign_id, user)
