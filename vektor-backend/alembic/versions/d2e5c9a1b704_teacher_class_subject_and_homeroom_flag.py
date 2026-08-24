"""teacher_classes: предмет и флаг классного руководителя

Этап 7m. Связь «учитель ↔ класс» получает собственные атрибуты:

  subject     — предметная роль в ЭТОМ классе («литература»), свободный текст.
                Один учитель ведёт разные предметы в разных классах, поэтому
                поле на связке, а не на users.
  is_homeroom — классный руководитель. Их может быть НЕСКОЛЬКО на класс, что
                и есть причина миграции: раньше это был единственный FK
                school_classes.homeroom_teacher_id.

Перенос: каждый нынешний homeroom_teacher_id проставляется флагом в своей
строке teacher_classes; если пары не было (сервис такого не допускал, но в
БД это возможно) — строка вставляется, иначе руководитель потерялся бы.
После переноса колонка удаляется.

downgrade возвращает колонку и берёт ОДНОГО руководителя на класс (минимальный
teacher_id) — обратная операция лишена информации по построению: несколько
руководителей в один FK не помещаются.

Revision ID: d2e5c9a1b704
Revises: f1a2b3c4d5e6
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e5c9a1b704"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teacher_classes", sa.Column("subject", sa.String(length=100), nullable=True))
    op.add_column(
        "teacher_classes",
        sa.Column("is_homeroom", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # Кл. рук, который уже числится учителем класса, — просто флаг.
    op.execute(
        """
        UPDATE teacher_classes tc
        SET is_homeroom = true
        FROM school_classes sc
        WHERE sc.id = tc.class_id AND sc.homeroom_teacher_id = tc.teacher_id
        """
    )
    # Кл. рук без строки в teacher_classes — дозаводим, иначе он исчезнет.
    op.execute(
        """
        INSERT INTO teacher_classes (teacher_id, class_id, subject, is_homeroom)
        SELECT sc.homeroom_teacher_id, sc.id, NULL, true
        FROM school_classes sc
        WHERE sc.homeroom_teacher_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM teacher_classes tc
              WHERE tc.class_id = sc.id AND tc.teacher_id = sc.homeroom_teacher_id
          )
        """
    )

    op.drop_column("school_classes", "homeroom_teacher_id")


def downgrade() -> None:
    op.add_column(
        "school_classes",
        sa.Column("homeroom_teacher_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_school_classes_homeroom_teacher_id_users",
        "school_classes",
        "users",
        ["homeroom_teacher_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE school_classes sc
        SET homeroom_teacher_id = (
            SELECT MIN(tc.teacher_id) FROM teacher_classes tc
            WHERE tc.class_id = sc.id AND tc.is_homeroom
        )
        """
    )
    op.drop_column("teacher_classes", "is_homeroom")
    op.drop_column("teacher_classes", "subject")
