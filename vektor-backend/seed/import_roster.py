"""Синхронизация состава школы с присланными списками 2026–2027.

    uv run python seed/import_roster.py            # dry-run: только отчёт
    uv run python seed/import_roster.py --apply    # запись одной транзакцией

Источник истины — каталог `data/` (см. seed/roster_parser.py). База при этом
не пересоздаётся: продолжающие ученики НАХОДЯТСЯ по «Фамилия Имя» и
обновляются на месте, поэтому их `assessments` остаются привязаны сами собой —
прошлую диагностику не нужно ни переносить, ни «прикреплять» отдельно.

Что делает:

* заводит недостающие классы и переименовывает секцию 5-«а» (см. ниже);
* дописывает ученикам отчество из списков, переводит между классами;
* заводит новых учеников (учётка `familiya.imya@vektor.ru`, общий пароль
  `BULK_DEFAULT_PASSWORD` — временная схема Этапа 3.7);
* выбывших (есть в БД с классом, нет в списках) ДЕАКТИВИРУЕТ и открепляет от
  класса, но не удаляет: у каждого есть анкеты 2026 года, а `Assessment`
  хранит снапшот `subject_class_id`, поэтому прошлогоднее покрытие и средние
  остаются полными. Это то же правило «не нашёлся — значит выпускник», что в
  импорте выгрузки МО (Этап 6);
* заводит 24 кураторов и привязывает к классам с `subject = "куратор"`.

Чего НЕ делает и почему:

* 19 сотрудников из `crew.xlsx` (директор, завучи, предметники без
  кураторства) остаются незаведёнными: в файле у них только инициалы, а
  учётка собирается из имени. На диагностику это не влияет — оценивающих
  админ выбирает из учителей класса (Этап 7o);
* родителей не трогает вовсе — школа собирает согласия на обработку
  персональных данных, данных ещё нет;
* дату рождения из docx не пишет — поля под неё в `User` пока нет
  (отдельная ветка).

Скрипт идемпотентен: повторный запуск после `--apply` не меняет ничего.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

import sqlalchemy as sa
from roster_parser import ParsedClass, email_for, parse_data_dir, short_name_of, sort_key
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.config import settings
from vektor.core.database import async_session_factory
from vektor.core.security import hash_password

# Предмет на связке «учитель ↔ класс» для куратора. Куратор — НЕ классный
# руководитель (`is_homeroom`), это отдельная школьная роль: у каждого класса
# их двое, а руководителя школа не назначает вовсе.
CURATOR_SUBJECT = "куратор"

# Класс 5-«а» — след ручной миграции прошлого года: секции «а» в школе нет,
# классы называются 5.1 и 5.2. Строка не пустая — на неё ссылаются 37 анкет
# диагностики 2026 как на снапшот класса субъекта, поэтому удалить её нельзя,
# а завести рядом настоящий 5-2 мешает UniqueConstraint(grade, section) только
# после переименования. Переименование историю не искажает: те 12 учеников
# действительно учились в 5.2, просто класс был заведён под чужим именем.
SECTION_FIXES: dict[tuple[int, str], str] = {(5, "а"): "2"}


@dataclass
class Plan:
    renamed_classes: list[str] = field(default_factory=list)
    new_classes: list[str] = field(default_factory=list)
    updated_students: list[str] = field(default_factory=list)
    moved_students: list[str] = field(default_factory=list)
    new_students: list[str] = field(default_factory=list)
    withdrawn_students: list[str] = field(default_factory=list)
    new_teachers: list[str] = field(default_factory=list)
    new_links: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(
            getattr(self, name)
            for name in (
                "renamed_classes",
                "new_classes",
                "updated_students",
                "moved_students",
                "new_students",
                "withdrawn_students",
                "new_teachers",
                "new_links",
            )
        )


async def _load_state(session: AsyncSession) -> dict:
    classes = (
        await session.execute(sa.text("SELECT id, grade, section FROM school_classes"))
    ).all()
    people = (
        await session.execute(
            sa.text(
                "SELECT id, full_name, email, role, is_active, school_class_id "
                "FROM users WHERE is_placeholder = false"
            )
        )
    ).all()
    links = (
        await session.execute(sa.text("SELECT teacher_id, class_id, subject FROM teacher_classes"))
    ).all()
    return {
        "classes": {(row.grade, row.section): row.id for row in classes},
        "students": [p for p in people if p.role == "student"],
        "teachers": [p for p in people if p.role == "teacher"],
        "emails": {p.email: p for p in people},
        "links": {(row.teacher_id, row.class_id): row.subject for row in links},
    }


@dataclass(frozen=True)
class Person:
    """Минимум, нужный после вставки нового человека, — id и имя для отчёта."""

    id: int
    full_name: str


def _index_by_name(people: list, plan: Plan, kind: str) -> dict[str, object]:
    """Индекс «Фамилия Имя» → человек. Полные тёзки внутри одной роли сделали бы
    сверку неоднозначной, поэтому это не молчаливая перезапись, а проблема."""
    index: dict[str, object] = {}
    for person in people:
        key = sort_key(person.full_name)
        if key in index:
            plan.problems.append(
                f"полные тёзки среди {kind} в БД: «{person.full_name}» "
                f"(id {index[key].id} и {person.id}) — сверка по имени неоднозначна"
            )
            continue
        index[key] = person
    return index


async def build_plan(
    session: AsyncSession, parsed: list[ParsedClass], crew: dict
) -> tuple[Plan, list]:
    """Собрать план и отложенные операции записи.

    Классы и учителей приходится вставлять уже здесь: их id нужен, чтобы
    проставить ссылку ученикам и связкам. При dry-run вся транзакция
    откатывается, поэтому в базе не остаётся ничего (кроме съеденных значений
    последовательностей — на это идём осознанно, иначе пришлось бы городить
    предсказание id)."""
    plan = Plan()
    state = await _load_state(session)
    operations: list = []

    class_ids = dict(state["classes"])
    for (grade, section), new_section in SECTION_FIXES.items():
        if (grade, section) in class_ids and (grade, new_section) not in class_ids:
            class_id = class_ids.pop((grade, section))
            class_ids[(grade, new_section)] = class_id
            plan.renamed_classes.append(f"{grade}-{section} → {grade}-{new_section}")
            operations.append(
                lambda cid=class_id, s=new_section: session.execute(
                    sa.text("UPDATE school_classes SET section = :s WHERE id = :id"),
                    {"s": s, "id": cid},
                )
            )

    # --- классы -----------------------------------------------------------
    for parsed_class in parsed:
        key = (parsed_class.grade, parsed_class.section)
        if key not in class_ids:
            class_ids[key] = (
                await session.execute(
                    sa.text(
                        "INSERT INTO school_classes (grade, section) VALUES (:g, :s) RETURNING id"
                    ),
                    {"g": parsed_class.grade, "s": parsed_class.section},
                )
            ).scalar_one()
            plan.new_classes.append(parsed_class.label)

    # --- ученики ----------------------------------------------------------
    students_by_name = _index_by_name(state["students"], plan, "учеников")
    hashed = hash_password(settings.bulk_default_password)
    seen_keys: set[str] = set()

    for parsed_class in parsed:
        class_id = class_ids[(parsed_class.grade, parsed_class.section)]
        for student in parsed_class.students:
            key = sort_key(student.full_name)
            seen_keys.add(key)
            existing = students_by_name.get(key)
            if existing is None:
                email = email_for(student.full_name)
                if email in state["emails"]:
                    plan.problems.append(
                        f"адрес {email} для нового ученика «{student.full_name}» "
                        f"уже занят: «{state['emails'][email].full_name}»"
                    )
                    continue
                state["emails"][email] = student
                plan.new_students.append(f"{parsed_class.label}: {student.full_name} <{email}>")
                operations.append(
                    lambda s=student, cid=class_id, e=email: session.execute(
                        sa.text(
                            "INSERT INTO users (email, hashed_password, full_name, role, "
                            "is_active, is_placeholder, school_class_id) VALUES "
                            "(:e, :h, :n, 'student', true, false, :cid)"
                        ),
                        {"e": e, "h": hashed, "n": s.full_name, "cid": cid},
                    )
                )
                continue

            changes: dict = {}
            if existing.full_name != student.full_name:
                changes["full_name"] = student.full_name
                plan.updated_students.append(f"«{existing.full_name}» → «{student.full_name}»")
            if existing.school_class_id != class_id:
                changes["school_class_id"] = class_id
                plan.moved_students.append(f"{student.full_name} → {parsed_class.label}")
            if not existing.is_active:
                changes["is_active"] = True
                plan.updated_students.append(f"{student.full_name}: снова активен")
            if changes:
                assignments = ", ".join(f"{column} = :{column}" for column in changes)
                operations.append(
                    lambda c=dict(changes, id=existing.id), a=assignments: session.execute(
                        sa.text(f"UPDATE users SET {a} WHERE id = :id"), c
                    )
                )

    # Выбывшие: числятся в классе, но в списках школы их нет. Только те, у кого
    # класс есть, — учётки без класса это выпускники прошлых лет, уже
    # обработанные импортом МО, и трогать их нечего.
    for existing in state["students"]:
        if existing.school_class_id is None or sort_key(existing.full_name) in seen_keys:
            continue
        plan.withdrawn_students.append(existing.full_name)
        operations.append(
            lambda sid=existing.id: session.execute(
                sa.text(
                    "UPDATE users SET is_active = false, school_class_id = NULL WHERE id = :id"
                ),
                {"id": sid},
            )
        )

    # --- кураторы ---------------------------------------------------------
    teachers_by_name = _index_by_name(state["teachers"], plan, "учителей")
    for parsed_class in parsed:
        class_id = class_ids[(parsed_class.grade, parsed_class.section)]
        for curator in parsed_class.curators:
            key = sort_key(curator)
            existing = teachers_by_name.get(key)
            if existing is None:
                email = email_for(curator)
                if email in state["emails"]:
                    plan.problems.append(
                        f"адрес {email} для куратора «{curator}» уже занят: "
                        f"«{state['emails'][email].full_name}»"
                    )
                    continue
                position = crew.get(short_name_of(curator).replace(" ", ""))
                teacher_id = (
                    await session.execute(
                        sa.text(
                            "INSERT INTO users (email, hashed_password, full_name, role, "
                            "is_active, is_placeholder) VALUES "
                            "(:e, :h, :n, 'teacher', true, false) RETURNING id"
                        ),
                        {"e": email, "h": hashed, "n": curator},
                    )
                ).scalar_one()
                state["emails"][email] = curator
                existing = Person(id=teacher_id, full_name=curator)
                teachers_by_name[key] = existing
                plan.new_teachers.append(
                    f"{curator} <{email}>"
                    + (f" — {position.position}" if position else " — должности в crew нет")
                )

            if (existing.id, class_id) not in state["links"]:
                state["links"][(existing.id, class_id)] = CURATOR_SUBJECT
                plan.new_links.append(f"{parsed_class.label}: {existing.full_name}")
                operations.append(
                    lambda tid=existing.id, cid=class_id: session.execute(
                        sa.text(
                            "INSERT INTO teacher_classes (teacher_id, class_id, subject, "
                            "is_homeroom) VALUES (:t, :c, :s, false)"
                        ),
                        {"t": tid, "c": cid, "s": CURATOR_SUBJECT},
                    )
                )

    return plan, operations


def report(plan: Plan) -> None:
    sections = [
        ("Переименованы классы", plan.renamed_classes),
        ("Заведены классы", plan.new_classes),
        ("Уточнены ФИО / статус", plan.updated_students),
        ("Переведены в другой класс", plan.moved_students),
        ("Новые ученики", plan.new_students),
        ("Выбывшие (деактивация + открепление)", plan.withdrawn_students),
        ("Новые учителя-кураторы", plan.new_teachers),
        ("Привязки «куратор → класс»", plan.new_links),
    ]
    for title, items in sections:
        print(f"\n{title}: {len(items)}")
        for item in items:
            print(f"    {item}")
    if plan.problems:
        print(f"\nПРОБЛЕМЫ: {len(plan.problems)}")
        for problem in plan.problems:
            print(f"    {problem}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="записать в БД")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    parsed, crew = parse_data_dir(args.data_dir)
    print(
        f"Разобрано: классов {len(parsed)}, "
        f"учеников {sum(len(c.students) for c in parsed)}, "
        f"кураторов {sum(len(c.curators) for c in parsed)}, "
        f"строк педсостава {len(crew)}"
    )

    async with async_session_factory() as session:
        plan, operations = await build_plan(session, parsed, crew)
        report(plan)

        if plan.problems:
            print("\nЗапись отменена: сначала разберите проблемы выше.")
            await session.rollback()
            return 1
        if not args.apply:
            print("\nDRY-RUN: в базу ничего не записано. Повторите с --apply.")
            await session.rollback()
            return 0
        if not plan.has_changes:
            print("\nИзменений нет — база уже соответствует спискам.")
            await session.rollback()
            return 0

        for operation in operations:
            await operation()
        await session.commit()
        print(f"\nЗаписано. Пароль новых учёток: {settings.bulk_default_password}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
