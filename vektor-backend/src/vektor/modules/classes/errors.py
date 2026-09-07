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


class PromotionAlreadyRun(DomainError):
    """За текущий учебный год перевод уже выполнен (есть активный PromotionRun)."""

    status_code = 409
    code = "promotion_already_run"
    message = "Перевод за этот учебный год уже выполнен"


class PromotionConfirmMismatch(DomainError):
    """confirm_academic_year не совпал с текущим учебным годом — защита от
    случайного запуска."""

    status_code = 422
    code = "promotion_confirm_mismatch"
    message = "Подтверждение учебного года не совпадает"


class PromotionRunNotFound(DomainError):
    status_code = 404
    code = "promotion_run_not_found"
    message = "Запуск перевода не найден"


class PromotionUndoBlocked(DomainError):
    """После перевода уже создана кампания — откат сломал бы её состав."""

    status_code = 409
    code = "promotion_undo_blocked"
    message = "Откат невозможен: после перевода уже создана кампания"


class PromotionAlreadyUndone(DomainError):
    status_code = 409
    code = "promotion_already_undone"
    message = "Этот перевод уже отменён"
