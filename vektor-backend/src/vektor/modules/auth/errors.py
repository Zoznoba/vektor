"""Доменные ошибки модуля auth.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class EmailAlreadyRegistered(DomainError):
    """Пользователь с таким email уже существует."""

    status_code = 409
    code = "email_already_registered"
    message = "Пользователь с таким email уже существует"
