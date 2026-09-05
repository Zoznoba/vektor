"""add subject_case snapshot to assessments

Третий снапшот на Assessment — по мотивам rater_role (a1c4e77b93f2) и
subject_class_id (e7b2065d94ac). Кейс субъекта фиксируется в момент генерации
и больше не пересчитывается.

Зачем: с этого среза кампания собирается не только из классов, но и из кейсов
(профильных групп). Кейс у ученика ровно один, и он МЕНЯЕТСЯ: переход из
одного кружка в другой — обычное дело. Если читать кейс из User.case_id при
чтении результатов, прошлогодняя диагностика задним числом «переедет» в новый
кружок, а старый останется без покрытия — ровно та же болезнь, от которой
subject_class_id лечит класс.

Nullable и без NOT NULL: у большинства анкет кейса нет вовсе (кампания по
классу), и это штатное состояние, а не пропуск данных.

Backfill НЕ делаем, в отличие от subject_class_id. Там текущий класс был
лучшим приближением, потому что видимость вопросов до миграции считалась
именно по нему. Здесь приближения нет: кейсы появились позже всех
существующих кампаний, ни одна из них по кейсам не собиралась, и проставить
нынешний кейс значило бы придумать факт — прошлые анкеты выданы не за кружок.

Revision ID: c7a4f1d9e230
Revises: 1bb952b43476
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a4f1d9e230"
down_revision: str | Sequence[str] | None = "1bb952b43476"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("subject_case_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_assessments_subject_case_id_cases"),
        "assessments",
        "cases",
        ["subject_case_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_assessments_subject_case_id_cases"),
        "assessments",
        type_="foreignkey",
    )
    op.drop_column("assessments", "subject_case_id")
