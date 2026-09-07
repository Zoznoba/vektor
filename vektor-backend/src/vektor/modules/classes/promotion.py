"""Чистая доменная часть ежегодного перевода классов: построение плана
перевода без БД.

Отдельный модуль по тем же причинам, что results/domain.py: это единственная
часть фичи, которую можно проверить на синтетике без базы
(юнит-тесты в tests/test_promotion.py), и единственное место, где живёт
доменное правило перевода. Здесь НЕТ ни одного импорта SQLAlchemy, и это
инвариант — как только сюда протечёт запрос, правило начнёт дублироваться по
местам применения (preview vs apply).

ГЛАВНОЕ ПРАВИЛО. Каждый класс grade N переходит в grade N+1; grade 11 —
выпуск. Целевая секция по умолчанию совпадает с исходной, КРОМЕ перехода в
10-й и 11-й классы: параллелей там нет, секция пустая, поэтому 9-1 и 9-2
сливаются в один класс «10» (many-to-one merge). Переходы группируются по
вычисленному ключу (target_grade, target_section), и списки учеников из
нескольких источников сливаются.

Прошлую статистику диагностики план НЕ трогает и трогать не может — она
держится на снапшотах Assessment.subject_class_id / subject_case_id /
rater_role, а план оперирует только текущим членством (User.school_class_id).
"""

from dataclasses import dataclass

# С 10 класса параллелей в школе нет — секция у 10 и 11 пустая.
_GRADELESS_SECTION_FROM_GRADE = 10
GRADUATION_GRADE = 11


@dataclass(frozen=True)
class StudentView:
    """Ученик в составе класса — ровно то, что нужно плану."""

    id: int
    is_active: bool


@dataclass(frozen=True)
class SchoolClassView:
    """Класс со списком учеников. Строится сервисом из ORM, чтобы доменная
    функция не зависела от SQLAlchemy."""

    id: int
    grade: int
    section: str
    students: tuple[StudentView, ...]


@dataclass(frozen=True)
class Transition:
    """Один переход: один или несколько исходных классов → один целевой."""

    target_grade: int
    target_section: str
    # None → класса ещё нет, будет создан на apply.
    target_class_id: int | None
    source_class_ids: tuple[int, ...]
    # Активные ученики, которых надо перевести (те, кто уже в целевом классе,
    # сюда НЕ попадают — идемпотентность).
    moving_student_ids: tuple[int, ...]
    # Ученики исходных классов, уже сидящие в целевом (частичный прошлый
    # прогон) — показать в предпросмотре, на apply пропустить.
    already_in_target_ids: tuple[int, ...]
    # >1 источника или целевой класс уже существует с учениками.
    merge: bool


@dataclass(frozen=True)
class GraduatingClass:
    """11-й класс: ученики уходят в выпуск (is_active=False, откреп от класса)."""

    class_id: int
    student_ids: tuple[int, ...]


@dataclass(frozen=True)
class SkippedItem:
    class_id: int
    reason: str  # "empty" | "inactive_students_left" | ...


@dataclass(frozen=True)
class PromotionPlan:
    transitions: tuple[Transition, ...] = ()
    graduating: tuple[GraduatingClass, ...] = ()
    skipped: tuple[SkippedItem, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def total_moving(self) -> int:
        return sum(len(t.moving_student_ids) for t in self.transitions)

    @property
    def total_graduating(self) -> int:
        return sum(len(g.student_ids) for g in self.graduating)

    @property
    def classes_to_create(self) -> int:
        return sum(1 for t in self.transitions if t.target_class_id is None)


def default_target_section(source_grade: int, source_section: str) -> str:
    """Целевая секция по умолчанию. Переход в 10/11 обнуляет секцию —
    параллелей там нет."""
    if source_grade + 1 >= _GRADELESS_SECTION_FROM_GRADE:
        return ""
    return source_section


def plan_promotion(
    classes: list[SchoolClassView],
    section_overrides: dict[int, str] | None = None,
) -> PromotionPlan:
    section_overrides = section_overrides or {}

    by_key: dict[tuple[int, str], SchoolClassView] = {
        (c.grade, c.section): c for c in classes
    }

    skipped: list[SkippedItem] = []
    graduating: list[GraduatingClass] = []
    warnings: list[str] = []

    # Исходные классы, сгруппированные по целевому ключу (grade+1, section).
    groups: dict[tuple[int, str], list[SchoolClassView]] = {}

    for source in classes:
        active = [s for s in source.students if s.is_active]

        if not source.students:
            skipped.append(SkippedItem(class_id=source.id, reason="empty"))
            continue

        if source.grade == GRADUATION_GRADE:
            graduating.append(
                GraduatingClass(
                    class_id=source.id,
                    student_ids=tuple(s.id for s in active),
                )
            )
            if not active:
                skipped.append(SkippedItem(class_id=source.id, reason="empty"))
            continue

        target_grade = source.grade + 1
        target_section = section_overrides.get(
            source.id, default_target_section(source.grade, source.section)
        )
        groups.setdefault((target_grade, target_section), []).append(source)

    transitions: list[Transition] = []

    for (target_grade, target_section), sources in sorted(groups.items()):
        target = by_key.get((target_grade, target_section))
        existing_student_ids = (
            {s.id for s in target.students} if target is not None else set()
        )

        moving: list[int] = []
        already_in_target: list[int] = []
        seen: set[int] = set()

        for source in sources:
            for student in source.students:
                if not student.is_active or student.id in seen:
                    continue
                seen.add(student.id)
                if student.id in existing_student_ids:
                    already_in_target.append(student.id)
                else:
                    moving.append(student.id)

        target_had_students = bool(existing_student_ids - set(already_in_target))
        merge = len(sources) > 1 or target_had_students

        if merge and target_had_students:
            label = f"{target_grade}-{target_section}" if target_section else str(target_grade)
            warnings.append(
                f"В классе «{label}» уже есть ученики — они останутся, "
                "новые будут добавлены к ним."
            )

        transitions.append(
            Transition(
                target_grade=target_grade,
                target_section=target_section,
                target_class_id=target.id if target is not None else None,
                source_class_ids=tuple(s.id for s in sources),
                moving_student_ids=tuple(moving),
                already_in_target_ids=tuple(already_in_target),
                merge=merge,
            )
        )

    return PromotionPlan(
        transitions=tuple(transitions),
        graduating=tuple(graduating),
        skipped=tuple(skipped),
        warnings=tuple(warnings),
    )
