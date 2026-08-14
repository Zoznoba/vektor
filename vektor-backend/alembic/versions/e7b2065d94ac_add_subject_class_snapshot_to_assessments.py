"""add subject_class snapshot to assessments

Второй снапшот на Assessment, ровно по мотивам a1c4e77b93f2 (rater_role).
Класс субъекта фиксируется в момент генерации анкеты и больше не
пересчитывается.

Зачем: видимость условных вопросов (31–33, только для 9–11 классов) сейчас
считается от User.school_class — то есть от ТЕКУЩЕГО класса. Перевод ученика
из 8-го в 9-й — штатное ежегодное событие — задним числом «дорисовывал» бы
в прошлогодней анкете три вопроса, на которые никто не отвечал: анкета
переставала быть completed, а число вопросов в прогрессе менялось само собой.
Импорт истории делает это не гипотезой, а гарантией: там ученик заведомо был
в другом классе.

Nullable без backfill в NOT NULL: у субъекта может не быть класса вообще
(учитель как субъект пилотной кампании, ученик вне класса).

Revision ID: e7b2065d94ac
Revises: c3f81ad0e7b5
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2065d94ac"
down_revision: str | Sequence[str] | None = "c3f81ad0e7b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("subject_class_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_assessments_subject_class_id_school_classes"),
        "assessments",
        "school_classes",
        ["subject_class_id"],
        ["id"],
    )

    # Backfill: для уже сгенерированных анкет лучшее доступное приближение —
    # текущий класс субъекта. Это ровно те данные, по которым видимость
    # считалась до сих пор, так что поведение существующих анкет не меняется.
    op.execute(
        """
        UPDATE assessments a
        SET subject_class_id = u.school_class_id
        FROM users u
        WHERE u.id = a.subject_id
          AND u.school_class_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_assessments_subject_class_id_school_classes"),
        "assessments",
        type_="foreignkey",
    )
    op.drop_column("assessments", "subject_class_id")
