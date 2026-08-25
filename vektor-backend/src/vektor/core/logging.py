# Настройка логирования (Этап 7).
#
# До сих пор конфигурации не было вообще: модули звали logger.info/warning, а
# root-логгер оставался с дефолтами Python — часть записей просто не доходила
# до вывода, а формат зависел от того, кто первым дёрнул basicConfig.

import logging

from vektor.core.config import settings

# request_id в формате есть всегда: без него строки одного запроса невозможно
# собрать вместе, когда работает несколько клиентов сразу.
LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"


class _RequestIdFilter(logging.Filter):
    """Подставляет request_id тем записям, что пришли не из обработки запроса.

    Без этого logging падает на KeyError в формате: строки на старте
    приложения (bootstrap-админ, миграции) request_id не имеют.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    # force: uvicorn успевает настроить логирование раньше нас, и без сброса
    # наши хендлеры добавились бы вторыми — каждая строка дублировалась бы.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Библиотеки, которые шумят на INFO. SQL-эхо включается отдельно
    # (settings.db_echo) — это осознанный выбор, а не уровень логирования.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # httpx логирует каждый запрос на INFO — в тестах это дублирует наш
    # access-лог построчно.
    logging.getLogger("httpx").setLevel(logging.WARNING)
