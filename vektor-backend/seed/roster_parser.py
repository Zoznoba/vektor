"""Разбор присланных школой списков состава на 2026–2027 учебный год.

Чистый парсер: ни одного импорта SQLAlchemy, никакой сверки с БД — только
«файл → структуры». Сверка и запись живут в seed/import_roster.py.

Источники (каталог vektor-backend/data/, в git не коммитится — там настоящие
ФИО несовершеннолетних, см. корневой .gitignore):

* `5.docx` … `11.docx` — по файлу на параллель, внутри один или два класса.
  Блок класса: заголовок («5.1   каб. 2.6» либо «10 класс» отдельной строкой
  от «каб. 4.2»), строка «КУРАТОРЫ: …», ещё несколько ФИО кураторов, дальше
  ученики строкой «Фамилия Имя Отчество ДД.ММ.ГГГГ».
* `crew.xlsx` — НЕ xlsx, а TSV с таким расширением (openpyxl на нём падает
  `BadZipFile`). Педсостав: № / ФИО (инициалами) / Должность / Доп. нагрузка.

Кураторы в crew продублированы в «Доп. нагрузке» («куратор 8.1»), но у
Черкасовой А.Д. (5.1) и Ольховик С.П. (5.2) эта пометка пропущена, поэтому
источник истины по кураторству — docx, а crew даёт только должность.
"""

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Транслитерация под email `familiya.imya@vektor.ru`. Таблица не абстрактно
# «правильная», а ровно та, которой собраны адреса при импорте выгрузки МО
# (Этап 6): х→h, ц→c, щ→sch, й→y, я→ya. Код того импорта из репозитория
# удалён, таблица восстановлена по существующим адресам и проверена на всех
# 157 учениках в БД — расхождений ноль. Менять её нельзя: другой вариант
# («kh», «ts», «ia») выдаст второй адрес тому же человеку.
TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "-": "-",
}

# Заголовок класса: «5.1» (параллель с двумя классами) или «10 класс».
# Секция у 10 и 11 пустая — параллели в школе нет, и так же они заведены в БД
# (Этап 6, shared/class_label.py печатает такой класс как «10», а не «10-»).
_CLASS_NUMBERED = re.compile(r"^(\d{1,2})\.(\d)\b")
_CLASS_PLAIN = re.compile(r"^(\d{1,2})\s*класс\b", re.IGNORECASE)

# Ученик: ровно три слова с заглавной + дата рождения.
_STUDENT = re.compile(
    r"^([А-ЯЁ][а-яёА-ЯЁ\-]+)\s+([А-ЯЁ][а-яё\-]+)\s+([А-ЯЁ][а-яё\-]+)\s+"
    r"(\d{2})\.(\d{2})\.(\d{4})$"
)
# Куратор: те же три слова, но без даты. Хвостовые подчёркивания — следы
# бланка («Боровлев Данила Сергеевич________»).
_FIO = re.compile(r"^([А-ЯЁ][а-яёА-ЯЁ\-]+)\s+([А-ЯЁ][а-яё\-]+)\s+([А-ЯЁ][а-яё\-]+)$")


@dataclass(frozen=True)
class ParsedStudent:
    full_name: str
    birth_date: date


@dataclass
class ParsedClass:
    grade: int
    section: str
    curators: list[str] = field(default_factory=list)
    students: list[ParsedStudent] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.grade}.{self.section}" if self.section else str(self.grade)


@dataclass(frozen=True)
class CrewMember:
    number: int
    short_name: str  # «Долгих Ю.А.» — полного ФИО в crew нет
    position: str
    extra: str


def transliterate(value: str) -> str:
    return "".join(TRANSLIT.get(ch, ch) for ch in value.lower())


def email_for(full_name: str) -> str:
    """`Иванова София Николаевна` → `ivanova.sofiya@vektor.ru`.

    Отчество в адрес не идёт: так собраны все существующие учётки, и добавить
    его сейчас значило бы выдать второй адрес тем, кто уже в базе.
    """
    parts = full_name.split()
    return f"{transliterate(parts[0])}.{transliterate(parts[1])}@vektor.ru"


def short_name_of(full_name: str) -> str:
    """`Долгих Юлия Алексеевна` → `Долгих Ю.А.` — ключ сверки docx с crew.xlsx."""
    parts = full_name.split()
    if len(parts) != 3:
        return full_name
    return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."


def sort_key(full_name: str) -> str:
    """Ключ сопоставления человека с БД: «Фамилия Имя» без отчества.

    В базе имена лежат именно так — выгрузка МО отчеств не содержала, — а в
    docx они полные. Email ключом не годится: он собирается транслитерацией,
    и любое расхождение в таблице породило бы дубль вместо совпадения.
    """
    parts = full_name.split()
    return " ".join(parts[:2]).replace("ё", "е").replace("Ё", "Е").lower()


def _paragraphs(path: Path) -> list[str]:
    document = ElementTree.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    lines = []
    for paragraph in document.iter(W + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W + "t"))
        text = text.replace("\xa0", " ").strip()
        if text:
            lines.append(text)
    return lines


def parse_classes_docx(path: Path) -> list[ParsedClass]:
    """Разобрать один файл параллели. Внутри 1–2 класса."""
    result: list[ParsedClass] = []
    current: ParsedClass | None = None
    in_curators = False

    for line in _paragraphs(path):
        numbered = _CLASS_NUMBERED.match(line)
        plain = _CLASS_PLAIN.match(line)
        if numbered or plain:
            grade = int((numbered or plain).group(1))
            section = numbered.group(2) if numbered else ""
            current = ParsedClass(grade=grade, section=section)
            result.append(current)
            in_curators = False
            continue

        if current is None:
            continue

        if line.upper().startswith("КУРАТОР"):
            in_curators = True
            _, _, tail = line.partition(":")
            tail = tail.strip().strip("_ ")
            if _FIO.match(tail):
                current.curators.append(tail)
            continue

        student = _STUDENT.match(line)
        if student:
            in_curators = False
            surname, name, patronymic, day, month, year = student.groups()
            current.students.append(
                ParsedStudent(
                    full_name=f"{surname} {name} {patronymic}",
                    birth_date=date(int(year), int(month), int(day)),
                )
            )
            continue

        if in_curators:
            candidate = line.strip("_ ")
            if _FIO.match(candidate):
                current.curators.append(candidate)

    return result


def parse_crew(path: Path) -> dict[str, CrewMember]:
    """Педсостав, ключ — фамилия с инициалами («Долгих Ю.А.»)."""
    crew: dict[str, CrewMember] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        member = CrewMember(
            number=int(cells[0]),
            short_name=cells[1],
            position=cells[2],
            extra=cells[3] if len(cells) > 3 else "",
        )
        crew[member.short_name.replace(" ", "")] = member
    return crew


def parse_data_dir(data_dir: Path) -> tuple[list[ParsedClass], dict[str, CrewMember]]:
    classes: list[ParsedClass] = []
    for grade in range(5, 12):
        path = data_dir / f"{grade}.docx"
        if not path.exists():
            raise FileNotFoundError(f"нет файла параллели: {path}")
        classes.extend(parse_classes_docx(path))
    classes.sort(key=lambda c: (c.grade, c.section))
    return classes, parse_crew(data_dir / "crew.xlsx")
