from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.competencies.models import Competency


async def list_competencies(db: AsyncSession) -> Sequence[Competency]:
    # outcome_area догружаем явно: она уходит в CompetencyOut, а ленивая
    # подгрузка при сериализации в async-контексте даёт MissingGreenlet.
    result = await db.execute(
        select(Competency)
        .options(selectinload(Competency.questions), selectinload(Competency.outcome_area))
        .order_by(Competency.order)
    )
    return result.scalars().all()
