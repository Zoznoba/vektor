# Ограничение частоты запросов (Этап 7).
#
# Ставится точечно, а не на всё подряд: смысл здесь — затруднить перебор
# паролей и массовое создание учёток, а не резать обычную работу с анкетами.
# Ученик, быстро проходящий 33 вопроса, под лимит попадать не должен.
#
# СЧЁТЧИК В REDIS, А НЕ В ПАМЯТИ. В памяти он живёт внутри одного процесса:
# при нескольких воркерах uvicorn лимит молча умножается на их число, а при
# перезапуске обнуляется — то есть защищает ровно до первого деплоя.
#
# ПРИ НЕДОСТУПНОМ REDIS ЗАПРОС ПРОПУСКАЕТСЯ (fail-open), с предупреждением в
# лог. Это осознанный компромисс: ограничение частоты — смягчающая мера, а не
# проверка прав. Сделать его жёсткой зависимостью означало бы, что падение
# Redis превращается в полную невозможность войти в систему — для школьной
# платформы это хуже, чем временно ослабленная защита от перебора. Обратная
# сторона честно называется: тот, кто уронит Redis, обойдёт и лимит.

import logging

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from vektor.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis:
    """Ленивый общий клиент. Соединение не устанавливается до первой команды,
    поэтому импорт модуля безопасен и без поднятого Redis."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def client_key(request: Request) -> str:
    """Идентификатор клиента для счётчика.

    За обратным прокси реальный адрес приходит в X-Forwarded-For — берём
    первый элемент цепочки. Заголовку можно верить только потому, что снаружи
    его выставляет наш же прокси; при прямом доступе к приложению его
    подделает кто угодно, поэтому в проде API не должен торчать напрямую.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit_setting: str, window_setting: str):
    """Зависимость FastAPI: не более N запросов за окно, оба из настроек.

    Пороги читаются ИЗ SETTINGS В МОМЕНТ ЗАПРОСА, а не захватываются при
    сборке зависимости. Иначе значения замерзали бы на импорте модуля, и ни
    выключить лимит в тестах, ни поменять порог без перезапуска было бы
    нельзя — а тестам это нужно: они делают десятки логинов подряд и любой
    разумный порог пробивают.

    Окно фиксированное (INCR + EXPIRE на первом запросе) — самый дешёвый
    вариант: одна команда на запрос, память освобождается сама. Минус
    известен: на стыке двух окон теоретически проходит до 2×limit. Для защиты
    от перебора паролей это несущественно, скользящее окно тут было бы
    усложнением без выигрыша.
    """

    async def checker(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return

        limit: int = getattr(settings, limit_setting)
        window_seconds: int = getattr(settings, window_setting)
        key = f"ratelimit:{scope}:{client_key(request)}"
        try:
            redis = get_redis()
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, window_seconds)
        except Exception as err:
            logger.warning(
                "Rate limit пропущен: Redis недоступен (%s). Ключ %s",
                err,
                key,
                extra={"request_id": getattr(request.state, "request_id", "-")},
            )
            return

        if current > limit:
            ttl = await _safe_ttl(redis, key, window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Слишком много попыток. Повторите через {ttl} с.",
                headers={"Retry-After": str(ttl)},
            )

    return Depends(checker)


async def _safe_ttl(redis: Redis, key: str, fallback: int) -> int:
    try:
        ttl = await redis.ttl(key)
    except Exception:
        return fallback
    # -1: ключ без TTL, -2: ключа уже нет. И то и другое — гонка между INCR и
    # EXPIRE; отдаём окно целиком, чтобы Retry-After не был отрицательным.
    return ttl if ttl > 0 else fallback
