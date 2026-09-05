"""Доменные ошибки модуля competencies.

Вынесены из service.py: исключения — часть контракта модуля (их статус и
машинный код видит клиент), их импортируют соседние модули, и держать их в
одном файле с бизнес-логикой значило импортировать сервис ради ошибки.
"""

from vektor.core.errors import DomainError


class VersionNotFound(DomainError):
    status_code = 404
    code = "questionnaire_version_not_found"
    message = "Редакция анкеты не найдена"


class VersionNotDraft(DomainError):
    """Структуру можно менять только в черновике — опубликованная редакция
    заморожена навсегда, иначе задним числом поехала бы историческая
    аналитика по кампаниям, которые её уже используют."""

    status_code = 409
    code = "questionnaire_version_not_draft"
    message = "Редактировать можно только черновик"


class DraftAlreadyExists(DomainError):
    """Одновременно редактируется не больше одного черновика — иначе
    is_draft на Competency/OutcomeArea не сказал бы, какому черновику
    принадлежит строка."""

    status_code = 409
    code = "draft_already_exists"
    message = "Черновик уже существует — опубликуйте или отмените его, прежде чем создавать новый"


class NoCurrentQuestionnaireVersion(DomainError):
    """Ни одна редакция анкеты не помечена действующей — не по чему создавать
    кампанию. В норме недостижимо: миграция c3f81ad0e7b5 ставит флаг, а
    частичный уникальный индекс не даёт завести вторую действующую.

    Раньше это исключение не ловил никто, и вместо осмысленного ответа клиент
    получал 500 — ровно тот случай, ради которого заведён общий обработчик.
    """

    status_code = 409
    code = "no_current_questionnaire_version"
    message = "Нет действующей редакции анкеты"


class EmptyQuestionnaire(DomainError):
    status_code = 409
    code = "empty_questionnaire"
    message = "В черновике нет ни одного вопроса — публиковать нечего"


class OutcomeAreaNotFound(DomainError):
    status_code = 404
    code = "outcome_area_not_found"
    message = "«ОР / навык» не найдена"


class CompetencyNotFound(DomainError):
    status_code = 404
    code = "competency_not_found"
    message = "Критерий не найден"


class QuestionNotFound(DomainError):
    status_code = 404
    code = "question_not_found"
    message = "Вопрос не найден"
