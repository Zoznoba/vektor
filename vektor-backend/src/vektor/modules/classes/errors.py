"""Доменные ошибки модуля classes.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class ClassAlreadyExists(DomainError):
    """Класс с таким grade+section уже существует."""

    status_code = 409
    code = "class_already_exists"
    message = "Класс с таким номером уже существует"


class ClassNotFound(DomainError):
    """Класс с таким id не найден."""

    status_code = 404
    code = "class_not_found"
    message = "Класс не найден"


class ClassNotEmpty(DomainError):
    """Класс нельзя удалить: в нём есть люди или накопилась история диагностик.

    Удаление пустого класса безопасно, а с составом или архивом кампаний —
    нет: молчаливое открепление всех разом слишком похоже на случайный клик, а
    снапшоты `Assessment.subject_class_id` без класса осиротеют. Зеркально
    CaseNotEmpty. Конкретную причину уточняем в message на месте возбуждения.
    """

    status_code = 409
    code = "class_not_empty"
    message = "Класс не пустой — удалить нельзя"


class TeacherAlreadyAssigned(DomainError):
    """Один или несколько учителей уже привязаны к этому классу."""

    status_code = 409
    code = "teacher_already_assigned"
    message = "Учитель уже привязан к этому классу"


class TeacherNotInClass(DomainError):
    """Учитель не привязан к этому классу — нечего править или откреплять."""

    status_code = 404
    code = "teacher_not_in_class"
    message = "Учитель не привязан к этому классу"


class StudentNotInClass(DomainError):
    """Ученик числится не в этом классе — открепление относится не к нему."""

    status_code = 404
    code = "student_not_in_class"
    message = "Ученик не числится в этом классе"
