# Единый формат ошибок API (Этап 7).
#
# До этого каждый роутер сам ловил доменные исключения и переводил их в
# HTTPException — 38 почти одинаковых блоков try/except на 6 модулей. Помимо
# объёма это давало две настоящие проблемы:
#
#   1. Незакрытое исключение = 500. Так, NoCurrentQuestionnaireVersion не ловил
#      никто, и вместо осмысленного 409 клиент получал бы Internal Server Error.
#   2. Разъезжающийся формат. FastAPI кладёт в `detail` СТРОКУ для HTTPException
#      и СПИСОК объектов для ошибок валидации. Фронт (api/client.ts) читает
#      `detail` только если это строка, поэтому любая 422 показывалась
#      пользователю как «Ошибка запроса (422)» — без единого намёка, что не так.
#
# Теперь маппинг живёт на самих исключениях (status_code + code), а роутеры
# просто не ловят их. Формат ответа один на все случаи:
#
#     {"detail": "человекочитаемое сообщение",
#      "code": "machine_readable_code",
#      "errors": [{"field": "body.value", "message": "..."}]}
#
# `detail` — ВСЕГДА строка, в том числе для валидации: это сохраняет
# совместимость с существующим фронтом и заодно чинит пункт 2.
# `errors` присутствует только там, где есть разбор по полям.

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """База доменных ошибок: сама знает свой HTTP-статус и машинный код.

    Подклассы задают status_code/code/message. `message` можно переопределить
    в точке возбуждения — одна и та же ошибка бывает про разное:
    CampaignNotActive — это и «закрыть можно только активную кампанию», и
    «приём ответов закрыт».
    """

    status_code: int = 400
    code: str = "domain_error"
    message: str = "Ошибка запроса"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


def error_response(
    status_code: int,
    detail: str,
    code: str,
    errors: list[dict] | None = None,
    headers: dict[str, str] | None = None,
    request: Request | None = None,
) -> JSONResponse:
    content: dict = {"detail": detail, "code": code}
    if errors:
        content["errors"] = errors
    # id запроса кладём в тело: пользователю есть что приложить к обращению, а
    # в логах строка находится за один grep. Ставит его RequestContextMiddleware;
    # в тестах, где middleware не подключён, поля просто не будет.
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if request_id:
        content["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=content, headers=headers)


# Коды под стандартные HTTP-статусы: фронту нужен стабильный машинный
# идентификатор и там, где ошибку возбудил не наш домен, а сам FastAPI
# (401 из get_current_user, 403 из require_role, 404 несуществующего роута).
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "unprocessable_entity",
    429: "too_many_requests",
    500: "internal_error",
}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return error_response(exc.status_code, exc.message, exc.code, request=request)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # exc.headers обязателен к переносу: на 401 там WWW-Authenticate, без
    # которого ответ перестаёт быть корректным challenge'ем.
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return error_response(
        exc.status_code,
        detail,
        _HTTP_CODES.get(exc.status_code, "http_error"),
        headers=getattr(exc, "headers", None),
        request=request,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Ошибки валидации Pydantic → тот же формат, что и у всех остальных.

    Раньше сюда уходил список объектов в `detail`, и фронт его не показывал.
    Теперь: `detail` — читаемая строка про первую проблему, `errors` — полный
    разбор по полям для подсветки инпутов.
    """
    errors = [
        {
            # loc вида ("body", "answers", 0, "value") → "body.answers.0.value"
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    first = errors[0] if errors else None
    detail = (
        f"Проверьте поле «{first['field']}»: {first['message']}"
        if first
        else "Данные запроса не прошли валидацию"
    )
    return error_response(422, detail, "validation_error", errors=errors, request=request)


def register_error_handlers(app: FastAPI) -> None:
    """Подключить обработчики. Вызывается в create_app до роутеров."""
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
