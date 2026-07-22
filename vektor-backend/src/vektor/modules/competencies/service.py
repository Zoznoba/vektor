from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from vektor.modules.competencies.models import Competency


async def list_competencies(db: AsyncSession) -> Sequence[Competency]:
    result = await db.execute(
        select(Competency).options(selectinload(Competency.questions)).order_by(Competency.order)
    )
    return result.scalars().all()
