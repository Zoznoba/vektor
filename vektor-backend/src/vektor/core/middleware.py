# Middleware: идентификатор запроса и access-лог (Этап 7).

import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("vektor.access")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Присваивает запросу id, логирует его исход и отдаёт id клиенту.

    id берётся из входящего заголовка, если он есть: за прокси или шлюзом
    сквозной идентификатор уже проставлен, и заводить свой означало бы порвать
    цепочку между нашими логами и логами перед нами.

    Кладётся в request.state — оттуда его читают обработчики ошибок
    (core/errors.py), чтобы вернуть id в теле ответа: пользователю есть что
    приложить к обращению, а в логах эта строка находится за один grep.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex[:12]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Необработанное исключение: залогировать с тем же id и пропустить
            # дальше. Иначе пятисотка осталась бы без единой строки в логе.
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s → 500 за %.0f мс",
                request.method,
                request.url.path,
                duration_ms,
                extra={"request_id": request_id},
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id

        # 5xx — наша вина, 4xx — обычно клиента: разный уровень, чтобы
        # алерты по ERROR не срабатывали на чужие опечатки в пароле.
        level = (
            logging.ERROR
            if response.status_code >= 500
            else logging.WARNING
            if response.status_code >= 400
            else logging.INFO
        )
        logger.log(
            level,
            "%s %s → %d за %.0f мс",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response
