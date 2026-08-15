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

# 4. Миграции БД
uv run alembic upgrade head

# 5. Запуск
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

## Миграции (Alembic)

```bash
uv run alembic upgrade head                 # применить все миграции
uv run alembic downgrade -1                 # откатить последнюю миграцию
uv run alembic revision --autogenerate -m "message"  # создать новую миграцию по изменениям моделей
uv run alembic history                      # история миграций
uv run alembic current                      # текущая версия БД
```

## Частые проблемы

**`permission denied ... /var/run/docker.sock`** — пользователь не в группе `docker`:

```bash
sudo usermod -aG docker $USER
# затем перелогиниться (или newgrp docker в текущем терминале)
```

**`ConnectionResetError` / `connection reset by peer` при подключении к Postgres**, хотя контейнер `healthy` — завис процесс `docker-proxy`, пробрасывающий порт 5432. Помогает пересоздание контейнеров (том с данными не удаляется):

```bash
docker compose down
docker compose up -d
```

## Статус

**Этап 1** — core готов: async-подключение к Postgres, `/health` реально пингует БД
(`SELECT 1`, при недоступной базе — 503). Дальше по этапам из `CLAUDE.md`.
