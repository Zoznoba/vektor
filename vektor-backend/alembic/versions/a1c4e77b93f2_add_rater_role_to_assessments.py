"""add rater_role to assessments

Роль оценивающего фиксируется в момент генерации анкеты и больше не
пересчитывается. Раньше результаты выводили её из ТЕКУЩИХ связей
(состав класса, привязка родителей) — из-за этого после перевода ученика
в следующий класс учитель прошлого года превращался в «одноклассника»:
его оценка пропадала из слоя teacher и попадала в пул анонимности peer.

Backfill существующих строк делаем тем же правилом, что и build_pairs,
с тем же приоритетом ролей: self > teacher > parent > peer.

Revision ID: a1c4e77b93f2
Revises: 10dbd2913430
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e77b93f2"
down_revision: str | Sequence[str] | None = "10dbd2913430"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Тип колонки — строковый enum, как у status в этой же таблице
# (native_enum=False → VARCHAR + CHECK через SQLAlchemy).
rater_role_type = sa.Enum(
    "self",
    "peer",
    "teacher",
    "parent",
    name="raterrole",
    native_enum=False,
    length=20,
)


def upgrade() -> None:
    # Сначала nullable — иначе существующие строки не пройдут NOT NULL.
    op.add_column("assessments", sa.Column("rater_role", rater_role_type, nullable=True))

    # 1) Самооценка: respondent совпадает с subject.
    op.execute(
        """
        UPDATE assessments
        SET rater_role = 'self'
        WHERE respondent_id = subject_id
        """
    )

    # 2) Учителя: респондент привязан к классу субъекта (teacher_classes).
    op.execute(
        """
        UPDATE assessments a
        SET rater_role = 'teacher'
        WHERE a.rater_role IS NULL
          AND EXISTS (
              SELECT 1
              FROM users u
              JOIN teacher_classes tc ON tc.class_id = u.school_class_id
              WHERE u.id = a.subject_id
                AND tc.teacher_id = a.respondent_id
          )
        """
    )

    # 3) Родители: связь parent_children (respondent — родитель субъекта).
    op.execute(
        """
        UPDATE assessments a
        SET rater_role = 'parent'
        WHERE a.rater_role IS NULL
          AND EXISTS (
              SELECT 1
              FROM parent_children pc
              WHERE pc.parent_id = a.respondent_id
                AND pc.child_id = a.subject_id
          )
        """
    )

    # 4) Всё остальное — одноклассники.
    op.execute("UPDATE assessments SET rater_role = 'peer' WHERE rater_role IS NULL")

    op.alter_column("assessments", "rater_role", nullable=False)


def downgrade() -> None:
    op.drop_column("assessments", "rater_role")
