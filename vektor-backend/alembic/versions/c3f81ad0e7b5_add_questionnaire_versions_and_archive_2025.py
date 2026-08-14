"""questionnaire versions, outcome areas, reseed competencies to 11 criteria

Две связанные вещи в одной миграции, потому что порознь они оставляют БД в
заведомо неверном состоянии.

1. Версия анкеты (QuestionnaireVersion). Импорт исторических данных приносит
   ДРУГУЮ редакцию инструмента: 4 из 11 критериев и один «ОР / навык»
   называются иначе, чем в 2026 году. Ответы обязаны остаться при своей
   редакции, иначе график динамики врёт молча.

2. Пересев справочника: 8 компетенций -> 11 критериев + 5 «ОР / навык».

Почему пересев вообще понадобился
---------------------------------
Сидинг 3909d9a917b9 группировал 33 вопроса по компетенциям ПО СМЫСЛУ: в форме
«Диагностика 360: июнь» заголовков секций не было, границы проставлялись на
глаз (см. пометку «гипотеза по смыслу» в CLAUDE.md, Этап 3). Файл результатов
МО принёс настоящую разметку — строки «ОР / навык» и «Критерий» над каждой
тройкой колонок. Гипотеза не подтвердилась: у школы 11 критериев ровно по 3
вопроса, сгруппированных в 5 ОР, а не 8 групп размером 2/4/3/2/4/5/7/6.

Побочный, но важный эффект: условность вопросов перестаёт быть свойством
ВОПРОСА и становится свойством КРИТЕРИЯ. В файле блок профпроб помечен
возрастом прямо в подписи — «Профессиональное самоопределение (9-11)».
Значит критерий либо считается целиком по трём вопросам, либо не считается
вовсе; «посчитан по неполному набору» не бывает.

Это чинит реальный дефект прежней модели: компетенция career содержала 7
вопросов, из них 3 условных, поэтому в 8 классе считалась по 4 вопросам, а в
9-м — по 7. Средний балл прыгал при переходе 8->9 не из-за ученика, а из-за
смены состава вопросов. Теперь возраст живёт на критерии (min_grade/max_grade),
а questions.is_conditional удаляется за ненадобностью.

Тексты вопросов редакции 2026 НЕ трогаем: формулировки не менялись, менялась
только наша группировка. Новой версии анкеты под это не заводим — иначе на
графике появился бы разрыв там, где содержательно ничего не произошло.

Revision ID: c3f81ad0e7b5
Revises: a1c4e77b93f2
Create Date: 2026-08-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f81ad0e7b5"
down_revision: str | Sequence[str] | None = "a1c4e77b93f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Таблицы для вставки объявляем через sa.table, а не через модели: миграция не
# должна зависеть от текущего состояния кода.
# ---------------------------------------------------------------------------

versions_table = sa.table(
    "questionnaire_versions",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("title", sa.String),
    sa.column("note", sa.String),
    sa.column("is_current", sa.Boolean),
)
outcome_areas_table = sa.table(
    "outcome_areas",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("order", sa.Integer),
)
competencies_table = sa.table(
    "competencies",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("order", sa.Integer),
    sa.column("outcome_area_id", sa.Integer),
    sa.column("min_grade", sa.Integer),
    sa.column("max_grade", sa.Integer),
)
questions_table = sa.table(
    "questions",
    sa.column("competency_id", sa.Integer),
    sa.column("text", sa.String),
    sa.column("order", sa.Integer),
    sa.column("version_id", sa.Integer),
)

CURRENT_VERSION_ID = 1
ARCHIVE_VERSION_ID = 2

CURRENT_VERSION_CODE = "2026.1"
CURRENT_VERSION_TITLE = "Диагностика 360 · 2026"

ARCHIVE_VERSION_CODE = "archive-2025"
ARCHIVE_VERSION_TITLE = "Диагностика 360 · архив 2025"

# Подпись на стыке версий («формулировки изменились, сравнение приблизительное»
# из прототипа). Держим в БД, а не во фронте: зависит от того, ЧТО за версия,
# а не от того, кто рисует график.
ARCHIVE_VERSION_NOTE = (
    "Формулировки четырёх критериев в этой редакции отличаются от действующей, "
    "сравнение по годам приблизительное."
)

# --- «ОР / навык»: 5 навыков на выходе. ----------------------------------
# В файле подписей ШЕСТЬ, но «Профессиональное самоопределение» встречается
# дважды — с суффиксами «(5-11)» и «(9-11)». Это не две области, а одна с
# двумя возрастными блоками (подтверждено автором методики: навыков пять).
# Возраст мы уже храним полями Competency.min_grade/max_grade, поэтому
# дублировать его ещё и разбиением ОР не нужно: суффикс из названия ушёл в
# данные, а области осталось пять.
OUTCOME_AREAS: list[tuple[int, str, str, int]] = [
    # (id, code, name, order)
    (1, "personal_identity", "Личное самоопределение", 0),
    (2, "goals_values", "Целеполагание и выбор на основе ценностей", 1),
    (3, "learning", "Умение учиться и применять знания", 2),
    (4, "career", "Профессиональное самоопределение", 3),
    (5, "active_life", "Активная жизненная позиция", 4),
]

# --- 11 критериев в порядке колонок файла. -------------------------------
# Ровно по 3 вопроса на критерий: колонки (i*3+1 .. i*3+3).
# Названия — редакции 2026 (лист «8.1 2026» целиком в ней). Отличия редакции
# 2025 не заводят новых критериев: это переименование, а не другой набор,
# поэтому живут в текстах архивных вопросов и в note архивной версии.
# min_grade/max_grade: NULL = без ограничения по классу.
NEW_COMPETENCY_ID_OFFSET = 100  # чтобы не пересечься со старыми id 1..8
CRITERIA: list[tuple[str, str, str, int | None, int | None]] = [
    # (code, name, outcome_area_code, min_grade, max_grade)
    ("self_awareness", "Самосознание", "personal_identity", None, None),
    ("emotional_intelligence", "Эмоциональный интеллект", "personal_identity", None, None),
    ("strengths_weaknesses", "Сильные и слабые стороны", "personal_identity", None, None),
    ("goal_setting", "Постановка целей", "goals_values", None, None),
    ("goal_planning", "Планирование пути к цели", "goals_values", None, None),
    (
        "learning_autonomy",
        "Умение самостоятельно учиться и проявлять любознательность",
        "learning",
        None,
        None,
    ),
    (
        "learning_transfer",
        "Умение управлять обучением и применять знания в новых ситуациях",
        "learning",
        None,
        None,
    ),
    (
        "career_self_awareness",
        "Самосознание в профессиональной деятельности",
        "career",
        5,
        11,
    ),
    ("proactive_stance", "Проактивная позиция", "active_life", None, None),
    ("responsibility", "Ответственность и адаптивность", "active_life", None, None),
    # Единственный критерий с возрастным порогом — бывшие is_conditional
    # вопросы. Заполнен только с 9 класса, сверено по данным файла.
    (
        "career_exploration",
        "Исследование профессиональных возможностей / профробы",
        "career",
        9,
        11,
    ),
]

# Названия критериев в редакции 2025 там, где они отличаются (номер колонки
# первой тройки -> название). Нужны только для текстов архивных вопросов.
CRITERIA_NAMES_2025: dict[int, str] = {
    16: "Умение планировать учебную деятельность",
    19: "Стремление к развитию",
    25: "Активное участие в жизни школы",
    28: "Ответственность и проактивность",
}

# --- Старый сидинг 3909d9a917b9: code -> id. -----------------------------
OLD_COMPETENCY_IDS: dict[str, int] = {
    "interests": 1,
    "emotional_intelligence": 2,
    "strengths_weaknesses": 3,
    "values": 4,
    "goal_setting": 5,
    "learning_feedback": 6,
    "career": 7,
    "proactivity": 8,
}

# Сквозная позиция вопроса 2026 (1..33) -> (code старой компетенции, order
# внутри неё). Порядок ровно тот, в котором вопросы лежат в списке QUESTIONS
# миграции 3909d9a917b9: группы 2/4/3/2/4/5/7/6.
OLD_SEED_LAYOUT: list[tuple[str, int]] = [
    (code, order)
    for code, count in [
        ("interests", 2),
        ("emotional_intelligence", 4),
        ("strengths_weaknesses", 3),
        ("values", 2),
        ("goal_setting", 4),
        ("learning_feedback", 5),
        ("career", 7),
        ("proactivity", 6),
    ]
    for order in range(count)
]

# Сквозная позиция вопроса 2026 -> номер колонки в файле.
# Позиции 1..24 совпадают. Хвост переставлен: старый сидинг поднял блок
# профпроб в компетенцию career, выше блока проактивности.
SEED_POSITION_TO_EXCEL_COLUMN: dict[int, int] = {n: n for n in range(1, 25)} | {
    25: 31,
    26: 32,
    27: 33,
    28: 25,
    29: 26,
    30: 27,
    31: 28,
    32: 29,
    33: 30,
}


def criterion_index_for_column(column: int) -> int:
    """Номер колонки файла (1..33) -> индекс критерия в CRITERIA (0..10)."""
    return (column - 1) // 3


def new_competency_id_for_column(column: int) -> int:
    return NEW_COMPETENCY_ID_OFFSET + criterion_index_for_column(column) + 1


def order_within_criterion(column: int) -> int:
    """Позиция вопроса внутри своего критерия: 0, 1 или 2."""
    return (column - 1) % 3


def archive_question_text(column: int) -> str:
    """Плейсхолдер вместо неизвестной формулировки архивной редакции.

    Осознанно НЕ выдумываем текст: он нигде не показывается (архивные анкеты
    никто не проходит, results отдаёт только агрегаты), а выдуманная
    формулировка потом читалась бы как настоящая. Название критерия берём
    в редакции 2025 — она отличается от действующей ровно в четырёх местах.
    """
    first_column = criterion_index_for_column(column) * 3 + 1
    name = CRITERIA_NAMES_2025.get(first_column, CRITERIA[criterion_index_for_column(column)][1])
    return f"[Архив 2025] Вопрос {column} · {name}"


# ---------------------------------------------------------------------------


def upgrade() -> None:
    # === 1. Справочник версий анкеты ===
    op.create_table(
        "questionnaire_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        # NULL — «сравнение корректно, оговорок нет».
        sa.Column("note", sa.String(length=500), nullable=True),
        # Действующая редакция — та, которую получают НОВЫЕ кампании. Ровно
        # одна (частичный уникальный индекс ниже); архивные всегда false.
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questionnaire_versions")),
        sa.UniqueConstraint("code", name=op.f("uq_questionnaire_versions_code")),
    )
    # Частичный индекс, а не обычный unique: false может повторяться сколько
    # угодно раз, true — ровно один.
    op.create_index(
        "uq_questionnaire_versions_current",
        "questionnaire_versions",
        ["is_current"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.bulk_insert(
        versions_table,
        [
            {
                "id": CURRENT_VERSION_ID,
                "code": CURRENT_VERSION_CODE,
                "title": CURRENT_VERSION_TITLE,
                "note": None,
                "is_current": True,
            },
            {
                "id": ARCHIVE_VERSION_ID,
                "code": ARCHIVE_VERSION_CODE,
                "title": ARCHIVE_VERSION_TITLE,
                "note": ARCHIVE_VERSION_NOTE,
                "is_current": False,
            },
        ],
    )
    # bulk_insert с явными id не двигает sequence — первый же INSERT из
    # приложения упал бы на дубликате первичного ключа.
    op.execute(
        "SELECT setval("
        "  pg_get_serial_sequence('questionnaire_versions', 'id'),"
        "  (SELECT MAX(id) FROM questionnaire_versions)"
        ")"
    )

    # === 2. questions.version_id: nullable -> backfill -> NOT NULL ===
    # В один шаг нельзя: 33 существующие строки не прошли бы NOT NULL.
    op.add_column("questions", sa.Column("version_id", sa.Integer(), nullable=True))
    op.execute(f"UPDATE questions SET version_id = {CURRENT_VERSION_ID}")
    op.alter_column("questions", "version_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_questions_version_id_questionnaire_versions"),
        "questions",
        "questionnaire_versions",
        ["version_id"],
        ["id"],
    )

    # === 3. campaigns.questionnaire_version_id — тем же порядком ===
    # Именно эта колонка отвечает на вопрос «какие вопросы показывать в анкетах
    # кампании». Без фильтра по ней активные кампании увидели бы 66 вопросов.
    op.add_column("campaigns", sa.Column("questionnaire_version_id", sa.Integer(), nullable=True))
    op.execute(f"UPDATE campaigns SET questionnaire_version_id = {CURRENT_VERSION_ID}")
    op.alter_column("campaigns", "questionnaire_version_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_campaigns_questionnaire_version_id_questionnaire_versions"),
        "campaigns",
        "questionnaire_versions",
        ["questionnaire_version_id"],
        ["id"],
    )

    # === 4. «ОР / навык» ===
    op.create_table(
        "outcome_areas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outcome_areas")),
        sa.UniqueConstraint("code", name=op.f("uq_outcome_areas_code")),
    )
    op.bulk_insert(
        outcome_areas_table,
        [
            {"id": oid, "code": code, "name": name, "order": order}
            for oid, code, name, order in OUTCOME_AREAS
        ],
    )
    op.execute(
        "SELECT setval("
        "  pg_get_serial_sequence('outcome_areas', 'id'),"
        "  (SELECT MAX(id) FROM outcome_areas)"
        ")"
    )

    # === 5. competencies: новые колонки ===
    # outcome_area_id пока nullable: старые 8 строк ещё живы и значения не имеют.
    op.add_column("competencies", sa.Column("outcome_area_id", sa.Integer(), nullable=True))
    op.add_column("competencies", sa.Column("min_grade", sa.Integer(), nullable=True))
    op.add_column("competencies", sa.Column("max_grade", sa.Integer(), nullable=True))

    # Старые code освобождаем: три из них (emotional_intelligence,
    # strengths_weaknesses, goal_setting) совпадают с новыми критериями и
    # упёрлись бы в UNIQUE до того, как старые строки удалятся.
    op.execute("UPDATE competencies SET code = 'legacy_' || code")

    outcome_area_ids = {code: oid for oid, code, _, _ in OUTCOME_AREAS}
    op.bulk_insert(
        competencies_table,
        [
            {
                "id": NEW_COMPETENCY_ID_OFFSET + index + 1,
                "code": code,
                "name": name,
                "description": None,
                "order": index,
                "outcome_area_id": outcome_area_ids[area_code],
                "min_grade": min_grade,
                "max_grade": max_grade,
            }
            for index, (code, name, area_code, min_grade, max_grade) in enumerate(CRITERIA)
        ],
    )

    # === 6. Перевешиваем вопросы редакции 2026 на новые критерии ===
    # Тексты не трогаем — меняется только принадлежность и порядок внутри
    # критерия. Сопоставление идёт по (старая компетенция, order), потому что
    # именно эта пара однозначно определяет вопрос в сидинге 3909d9a917b9.
    for position, (old_code, old_order) in enumerate(OLD_SEED_LAYOUT, start=1):
        column = SEED_POSITION_TO_EXCEL_COLUMN[position]
        op.execute(
            sa.text(
                'UPDATE questions SET competency_id = :new_id, "order" = :new_order '
                "WHERE version_id = :version_id "
                "  AND competency_id = :old_id "
                '  AND "order" = :old_order'
            ).bindparams(
                new_id=new_competency_id_for_column(column),
                new_order=order_within_criterion(column),
                version_id=CURRENT_VERSION_ID,
                old_id=OLD_COMPETENCY_IDS[old_code],
                old_order=old_order,
            )
        )

    # === 7. Убираем старые компетенции ===
    op.execute(f"DELETE FROM competencies WHERE id <= {NEW_COMPETENCY_ID_OFFSET}")
    op.execute(
        "SELECT setval("
        "  pg_get_serial_sequence('competencies', 'id'),"
        "  (SELECT MAX(id) FROM competencies)"
        ")"
    )
    op.alter_column("competencies", "outcome_area_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_competencies_outcome_area_id_outcome_areas"),
        "competencies",
        "outcome_areas",
        ["outcome_area_id"],
        ["id"],
    )

    # === 8. is_conditional переезжает с вопроса на критерий ===
    # Возраст теперь живёт в competencies.min_grade/max_grade и применяется
    # к тройке вопросов целиком.
    op.drop_column("questions", "is_conditional")

    # === 9. 33 архивных вопроса редакции 2025 ===
    # order — позиция внутри критерия (0..2), как и у действующей редакции:
    # импорт находит вопрос по паре (критерий колонки, (колонка-1) % 3).
    op.bulk_insert(
        questions_table,
        [
            {
                "competency_id": new_competency_id_for_column(column),
                "text": archive_question_text(column),
                "order": order_within_criterion(column),
                "version_id": ARCHIVE_VERSION_ID,
            }
            for column in range(1, 34)
        ],
    )


def downgrade() -> None:
    # Разворачиваем ровно в обратном порядке. Пересев обратим полностью:
    # раскладка старого сидинга известна константой, а тексты вопросов 2026
    # мы не меняли.
    op.execute(f"DELETE FROM questions WHERE version_id = {ARCHIVE_VERSION_ID}")

    op.add_column(
        "questions",
        sa.Column("is_conditional", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # Снять NOT NULL и FK ДО вставки старых компетенций: у них области
    # результата нет и быть не может — они из модели, где ОР не существовало.
    op.drop_constraint(
        op.f("fk_competencies_outcome_area_id_outcome_areas"), "competencies", type_="foreignkey"
    )
    op.alter_column("competencies", "outcome_area_id", nullable=True)

    # Зеркало приёма из upgrade: три критерия (emotional_intelligence,
    # strengths_weaknesses, goal_setting) носят те же code, что и старые
    # компетенции, и упёрлись бы в UNIQUE до своего удаления.
    op.execute("UPDATE competencies SET code = 'tmp_' || code")

    # Возвращаем старые 8 компетенций (id 1..8, исходные code/name/order).
    op.bulk_insert(
        competencies_table,
        [
            {
                "id": OLD_COMPETENCY_IDS[code],
                "code": code,
                "name": name,
                "description": None,
                "order": OLD_COMPETENCY_IDS[code] - 1,
                "outcome_area_id": None,
                "min_grade": None,
                "max_grade": None,
            }
            for code, name in [
                ("interests", "Самоопределение и интересы"),
                ("emotional_intelligence", "Эмоциональный интеллект"),
                ("strengths_weaknesses", "Сильные и слабые стороны"),
                ("values", "Ценности и решения"),
                ("goal_setting", "Целеполагание"),
                ("learning_feedback", "Работа с информацией и обратной связью"),
                ("career", "Профессиональное самоопределение"),
                ("proactivity", "Проактивность и ответственность"),
            ]
        ],
    )

    for position, (old_code, old_order) in enumerate(OLD_SEED_LAYOUT, start=1):
        column = SEED_POSITION_TO_EXCEL_COLUMN[position]
        # Условными были три вопроса профпроб — колонки 31..33.
        op.execute(
            sa.text(
                'UPDATE questions SET competency_id = :old_id, "order" = :old_order, '
                "  is_conditional = :is_conditional "
                "WHERE version_id = :version_id "
                "  AND competency_id = :new_id "
                '  AND "order" = :new_order'
            ).bindparams(
                old_id=OLD_COMPETENCY_IDS[old_code],
                old_order=old_order,
                is_conditional=column >= 31,
                version_id=CURRENT_VERSION_ID,
                new_id=new_competency_id_for_column(column),
                new_order=order_within_criterion(column),
            )
        )

    op.execute(f"DELETE FROM competencies WHERE id > {NEW_COMPETENCY_ID_OFFSET}")
    op.execute(
        "SELECT setval("
        "  pg_get_serial_sequence('competencies', 'id'),"
        "  (SELECT MAX(id) FROM competencies)"
        ")"
    )
    op.drop_column("competencies", "max_grade")
    op.drop_column("competencies", "min_grade")
    op.drop_column("competencies", "outcome_area_id")
    op.drop_table("outcome_areas")

    op.drop_constraint(
        op.f("fk_campaigns_questionnaire_version_id_questionnaire_versions"),
        "campaigns",
        type_="foreignkey",
    )
    op.drop_column("campaigns", "questionnaire_version_id")
    op.drop_constraint(
        op.f("fk_questions_version_id_questionnaire_versions"), "questions", type_="foreignkey"
    )
    op.drop_column("questions", "version_id")
    op.drop_index("uq_questionnaire_versions_current", table_name="questionnaire_versions")
    op.drop_table("questionnaire_versions")
