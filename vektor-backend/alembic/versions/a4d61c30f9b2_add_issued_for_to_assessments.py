"""add issued_for to assessments

Основание выдачи анкеты (класс или кейс) — четвёртый снапшот на Assessment
после rater_role, subject_class_id и subject_case_id, и по той же причине:
фиксируется при генерации и не пересчитывается при чтении.

Зачем: покрытие кампании группировалось правилом «есть кейс — строка кейса,
иначе класса» (results.domain.coverage_key). Правило врёт для ученика,
состоящего И в классе, И в кейсе: пары обоих оснований сливаются в ОДНУ
анкету с обоими снапшотами (subject_class_id проставляется всегда — от него
зависит видимость возрастных вопросов), поэтому в строку кейса уезжала вся
его диагностика, включая самооценку, родителей и учителей класса, а из
строки своего класса ученик пропадал вовсе.

Backfill повторяет прежнее правило: есть кейс — "case", иначе есть класс —
"class", иначе NULL. Это не придуманный факт: до этой миграции кампании
собирались так, что кейсовые анкеты выдавались только кейсом, а прежнее
поведение покрытия на существующих данных сохраняется один в один.

Revision ID: a4d61c30f9b2
Revises: d19bea8eab3b
Create Date: 2026-09-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d61c30f9b2"
down_revision: str | Sequence[str] | None = "d19bea8eab3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column(
            "issued_for",
            sa.Enum("class", "case", name="assessmentbasis", native_enum=False, length=20),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE assessments
           SET issued_for = CASE
                 WHEN subject_case_id IS NOT NULL THEN 'case'
                 WHEN subject_class_id IS NOT NULL THEN 'class'
               END
        """
    )


def downgrade() -> None:
    op.drop_column("assessments", "issued_for")
