"""add birth_date to users

Дата рождения у человека. Nullable и без backfill: в выгрузке МО (Этап 6),
из которой заведена вся школа, её нет вовсе — единственный источник — списки
состава 2026–2027 (`data/*.docx`), и там она есть только у учеников.

Колонка общая на все роли, а не «только ученику»: ограничение по роли было бы
правилом про данные, а не про схему, и хранить его в БД нечем — роль
меняется, а дата рождения остаётся той же.

Revision ID: f3c8a2d51e47
Revises: a4d61c30f9b2
Create Date: 2026-09-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3c8a2d51e47"
down_revision: str | Sequence[str] | None = "a4d61c30f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "birth_date")
