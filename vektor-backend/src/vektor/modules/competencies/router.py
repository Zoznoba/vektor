from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user
from vektor.modules.competencies import service
from vektor.modules.competencies.schemas import CompetencyOut
from vektor.modules.users.models import User

router = APIRouter(prefix="/competencies", tags=["competencies"])


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
