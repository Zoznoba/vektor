# Платформа Вектор — Backend

Backend для платформы 360° оценки компетенций (FastAPI + SQLAlchemy 2.0 async).

Архитектурные решения и дорожная карта — в [`CLAUDE.md`](./CLAUDE.md).

## Быстрый старт

Требуется [uv](https://docs.astral.sh/uv/) и Docker.

```bash
# 1. Зависимости
uv sync

# 2. Локальная инфраструктура (Postgres + Redis)
docker compose up -d

# 3. Переменные окружения
cp .env.example .env

# 4. Запуск
uv run uvicorn vektor.main:app --reload
```

Проверка: http://127.0.0.1:8000/health → `{"status":"ok"}`
Swagger: http://127.0.0.1:8000/docs

## Разработка

```bash
uv run pytest          # тесты
uv run ruff check .    # линтер
uv run ruff format .   # форматирование
```

## Статус

**Этап 1** — core готов: async-подключение к Postgres, `/health` реально пингует БД
(`SELECT 1`, при недоступной базе — 503). Дальше по этапам из `CLAUDE.md`.
