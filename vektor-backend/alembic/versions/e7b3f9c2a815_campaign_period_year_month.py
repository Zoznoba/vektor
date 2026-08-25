"""campaigns: период = год + месяц числами; окно приёма ответов удалено

Две правки в одной таблице, обе — упрощение.

1. period (String(20), свободный ярлык «2026» либо «2026-06») → period_year +
   period_month, оба NOT NULL. Формат ярлыка не был зафиксирован, поэтому
   хронологию периодов нельзя было выразить в ORDER BY: "2026" — префикс
   "2026-02" и лексикографически МЕНЬШЕ, хотя по смыслу не раньше. Разбор
   регуляркой (results.period_sort_key) удаляется вместе с колонкой.

   Backfill: год — первые 4 цифры ярлыка, месяц — группа после дефиса.
   ЯРЛЫК БЕЗ МЕСЯЦА («2026», «2025» — так заведены годовые кампании классов
   и архив) получает ИЮНЬ. Это осознанная подстановка, а не факт из данных:
   диагностику в школе проводят в июне (исходная форма так и называлась —
   «Диагностика 360: июнь»), но у архивной кампании 2025 месяца не
   существовало вовсе. Мусорные ярлыки, не подходящие под шаблон, получают
   год 1970 — чтобы строка не потерялась молча и была видна глазами.

2. opens_at / closes_at удалены. Они были декоративными: ни одна проверка в
   бэкенде на них не смотрела (приём ответов режется только
   CampaignStatus), а во всех боевых данных обе колонки стояли в NULL.
   Единственным потребителем был баннер ученика «до 20 июня», который уже
   умеет случай «дедлайна нет» и просто не показывает эту часть текста.

downgrade собирает ярлык обратно как «ГГГГ-ММ» — всегда с месяцем, потому что
различить «был годовым» и «был июньским» после upgrade нечем; opens_at /
closes_at возвращаются пустыми, данных для них не существует.

Revision ID: e7b3f9c2a815
Revises: d2e5c9a1b704
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3f9c2a815"
down_revision: str | Sequence[str] | None = "d2e5c9a1b704"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Ярлык без месяца — это учебный год целиком; подставляем месяц реального
# проведения диагностики. См. докстринг: подстановка, а не факт.
_DEFAULT_MONTH = 6


def upgrade() -> None:
    # Три шага, а не сразу NOT NULL: на непустой таблице так не пройдёт.
    op.add_column("campaigns", sa.Column("period_year", sa.Integer(), nullable=True))
    op.add_column("campaigns", sa.Column("period_month", sa.Integer(), nullable=True))

    op.execute(
        f"""
        UPDATE campaigns
        SET period_year = COALESCE(
                NULLIF(substring(period FROM '^(\\d{{4}})'), '')::int, 1970
            ),
            period_month = COALESCE(
                NULLIF(substring(period FROM '^\\d{{4}}-(\\d{{2}})'), '')::int,
                {_DEFAULT_MONTH}
            )
        """
    )

    op.alter_column("campaigns", "period_year", nullable=False)
    op.alter_column("campaigns", "period_month", nullable=False)

    op.drop_column("campaigns", "period")
    op.drop_column("campaigns", "opens_at")
    op.drop_column("campaigns", "closes_at")


def downgrade() -> None:
    op.add_column("campaigns", sa.Column("period", sa.String(length=20), nullable=True))
    op.execute(
        "UPDATE campaigns "
        "SET period = period_year::text || '-' || lpad(period_month::text, 2, '0')"
    )
    op.alter_column("campaigns", "period", nullable=False)

    op.add_column("campaigns", sa.Column("opens_at", sa.DateTime(), nullable=True))
    op.add_column("campaigns", sa.Column("closes_at", sa.DateTime(), nullable=True))

    op.drop_column("campaigns", "period_month")
    op.drop_column("campaigns", "period_year")
