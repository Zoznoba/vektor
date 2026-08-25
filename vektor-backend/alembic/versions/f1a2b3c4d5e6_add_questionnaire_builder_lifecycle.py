"""add questionnaire builder lifecycle (draft/publish, archive)

Стадия 7: у администратора появляется конструктор анкеты — редактирование
"ОР / навык" (outcome_areas), критериев (competencies) и вопросов черновиком
с последующей публикацией.

questionnaire_versions.status — жизненный цикл редакции: 'draft' редактируется
свободно, 'published' заморожен навсегда (тексты/структура не меняются).
Существующая действующая (и архивная) редакция уже фактически опубликована —
backfill проставляет 'published' обеим.

outcome_areas/competencies НЕ версионируются (в отличие от questions) — это
общий список критериев на все редакции разом, см. комментарий в
competencies/models.py. Поэтому у них нет version_id, а есть:
  - is_archived: критерий/область скрыты из новых черновиков, но не удалены —
    прошлые кампании и их результаты продолжают ссылаться на строку как есть.
  - is_draft: строка создана прямо в ещё не опубликованном черновике. При
    публикации (service.publish_version) флаг снимается у всех разом — ровно
    один черновик может существовать одновременно, поэтому неоднозначности
    "чей это черновик" не возникает. При отмене черновика такие строки
    удаляются целиком (service.discard_draft) — они никогда не успели никуда
    попасть, кроме своей же брошенной версии.

Revision ID: f1a2b3c4d5e6
Revises: b9d41f7c2a08
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "b9d41f7c2a08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questionnaire_versions",
        sa.Column("status", sa.String(length=20), nullable=True),
    )
    op.execute("UPDATE questionnaire_versions SET status = 'published'")
    op.alter_column("questionnaire_versions", "status", nullable=False)

    op.add_column(
        "outcome_areas",
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "outcome_areas",
        sa.Column("is_draft", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "competencies",
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "competencies",
        sa.Column("is_draft", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("competencies", "is_draft")
    op.drop_column("competencies", "is_archived")
    op.drop_column("outcome_areas", "is_draft")
    op.drop_column("outcome_areas", "is_archived")
    op.drop_column("questionnaire_versions", "status")
