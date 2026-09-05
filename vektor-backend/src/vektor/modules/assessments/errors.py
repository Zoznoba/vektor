"""Доменные ошибки модуля assessments.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class CampaignNotFound(DomainError):
    """Кампания с таким id не найдена."""

    status_code = 404
    code = "campaign_not_found"
    message = "Кампания не найдена"


class AssessmentNotFound(DomainError):
    """Анкета с таким id не найдена."""

    status_code = 404
    code = "assessment_not_found"
    message = "Анкета не найдена"


class NotAssessmentOwner(DomainError):
    """Пользователь пытается открыть/заполнить не свою анкету."""

    status_code = 403
    code = "not_assessment_owner"
    message = "Пользователь не является владельцем анкеты"


class CampaignNotClosed(DomainError):
    """Возобновить можно только завершённую кампанию."""

    status_code = 409
    code = "campaign_not_closed"
    message = "Возобновить можно только завершённую кампанию"


class CampaignNotActive(DomainError):
    """Кампания не в статусе active.

    Сообщение переопределяется в точке возбуждения: для приёма ответов это
    «прием закрыт», для закрытия кампании — «закрыть можно только активную».
    """

    status_code = 409
    code = "campaign_not_active"
    message = "Кампания не активна"


class QuestionNotAllowed(DomainError):
    """Ответ на вопрос, которого нет в видимом наборе этой анкеты."""

    status_code = 422
    code = "question_not_allowed"
    message = "Ответ на недоступный вопрос"
