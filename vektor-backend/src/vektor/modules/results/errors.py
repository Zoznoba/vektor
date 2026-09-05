"""Доменные ошибки модуля results.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class CampaignNotCompleted(DomainError):
    """Кампания существует, но ещё не завершена — результатов по ней нет."""

    status_code = 409
    code = "campaign_not_completed"
    message = "Результаты доступны только по завершённой кампании"


class SubjectNotFound(DomainError):
    """Пользователь-субъект с таким id не найден."""

    status_code = 404
    code = "subject_not_found"
    message = "Субъект не найден"


class NotAllowedToViewResults(DomainError):
    """Текущий пользователь не имеет права смотреть результаты этого субъекта."""

    status_code = 403
    code = "not_allowed_to_view_results"
    message = "Нет доступа к этим результатам"
