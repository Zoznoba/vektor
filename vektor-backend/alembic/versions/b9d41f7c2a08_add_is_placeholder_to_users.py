"""add is_placeholder to users

Явный флаг «служебный респондент-заглушка» вместо опознавания по домену почты.

Зачем: в выгрузке МО педагоги и родители обезличены — там нет ФИО вообще, только
метки строк («Педагог», «Педагог 2»). При этом `Assessment.respondent_id` — NOT NULL,
то есть завести кого-то на слот всё равно надо. Такие учётки создаются по одной на
(класс, роль, номер) и человеком не являются: «Педагог 2» у всех учеников класса —
один и тот же respondent_id, потому что правило анонимности считает РАЗНЫХ людей,
а не строки.

До сих пор они опознавались косвенно — по домену `@archive.vektor.*` плюс
`is_active=false`. Косвенный признак плох тем, что домен — это данные, а не схема:
любая выборка «настоящих учителей класса» вынуждена была бы фильтровать по LIKE
на email, и первый же реальный учитель с похожей почтой попал бы под раздачу.

Nullable не нужен: у существующих строк осмысленное значение false.

ВАЖНО про Revision ID. Этот файл — РЕКОНСТРУКЦИЯ. Демо-дамп (`seed/demo_data.sql`)
проштампован ревизией `b9d41f7c2a08`, созданной на другой машине; сам файл миграции
оттуда не попал в репозиторий, приехал только результат — дамп. ID проставлен
вручную именно таким, чтобы штамп внутри дампа резолвился: иначе после
восстановления база заявляла бы неизвестную Alembic ревизию и `upgrade head` вставал
бы намертво. Схема на выходе совпадает с дампом побайтно по DDL
(`is_placeholder boolean DEFAULT false NOT NULL`), сверено сравнением CREATE TABLE.

Revision ID: b9d41f7c2a08
Revises: e7b2065d94ac
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9d41f7c2a08"
down_revision: str | Sequence[str] | None = "e7b2065d94ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_placeholder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Backfill по домену — единственный признак, который был до появления флага.
    # Нужен для баз, поднятых из ПРЕДЫДУЩЕЙ редакции дампа (ревизия e7b2065d94ac):
    # там служебные учётки уже есть, но колонки ещё нет, и после upgrade они молча
    # стали бы «настоящими» людьми. На пустой базе это no-op.
    # Оба домена: ранняя редакция дампа использовала .local, поздняя — .ru.
    op.execute(
        """
        UPDATE users
        SET is_placeholder = true
        WHERE email LIKE '%@archive.vektor.local'
           OR email LIKE '%@archive.vektor.ru'
        """
    )


def downgrade() -> None:
    op.drop_column("users", "is_placeholder")
