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
