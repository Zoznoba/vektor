"""Доменные ошибки модуля users.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class UserNotFound(DomainError):
    """Один или несколько пользователей с такими id не найдены."""

    status_code = 404
    code = "user_not_found"
    message = "Пользователь не найден"


class WrongRole(DomainError):
    """Роль пользователя не подходит для операции."""

    status_code = 409
    code = "wrong_role"
    message = "Роль пользователя не подходит для операции"


class DuplicateEmailsInBatch(DomainError):
    """В самом присланном списке есть повторяющиеся email (до всякой БД)."""

    status_code = 422
    code = "duplicate_emails_in_batch"
    message = "В списке есть повторяющиеся email"


class EmailsAlreadyTaken(DomainError):
    """Один или несколько email уже заняты пользователями в БД."""

    status_code = 409
    code = "emails_already_taken"
    message = "Некоторые email уже заняты"


class CannotModifySelf(DomainError):
    """Админ пытается деактивировать сам себя."""

    status_code = 409
    code = "cannot_modify_self"
    message = "Нельзя изменить статус собственной учётной записи"
