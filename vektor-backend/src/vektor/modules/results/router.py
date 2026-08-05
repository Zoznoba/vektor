from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user
from vektor.modules.results import service
from vektor.modules.results.schemas import ResultsOut
from vektor.modules.users.models import User

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{subject_id}", response_model=ResultsOut)
async def get_results(
    subject_id: int,
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResultsOut:
    try:
        return await service.get_subject_results(db, subject_id, campaign_id, user)
    except service.CampaignNotFound as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Кампания не найдена"
        ) from err
    except service.SubjectNotFound as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Субъект не найден"
        ) from err
    except service.NotAllowedToViewResults as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к результатам этого пользователя",
        ) from err
