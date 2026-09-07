"""add self_text to questions

Альтернативная формулировка вопроса для самооценки (respondent == subject).
Родитель и учитель оценивают ученика одной и той же формулировкой («он …»), а
у самого ученика «я …» звучит иначе — обобщить нельзя. Поле точечное: NULL и
означает «тот же text для всех», заполняется лишь у нескольких вопросов.

Nullable без backfill: NULL — осмысленное значение по умолчанию.

Revision ID: d19bea8eab3b
Revises: c7a4f1d9e230
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d19bea8eab3b"
down_revision: str | Sequence[str] | None = "c7a4f1d9e230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("self_text", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "self_text")
