# Демо-данные

`demo_data.sql` — полный дамп базы (схема + данные) реальной диагностики всей
школы «Вектор»: 12 классов (5-1…9-2, 10, 11), два периода (2026 и архив 2025
там, где он есть), 19502 ответа. Снят на ревизии `c7a4f1d9e230` (head на
момент снятия) — `alembic upgrade head` после восстановления не обязателен,
но безопасен: если head к моменту восстановления уйдёт дальше, апгрейд всё
равно нужен.

```bash
make up                                    # Postgres + Redis
docker exec -i vektor-backend-db-1 psql -U vektor -d vektor < seed/demo_data.sql
uv run alembic upgrade head                # на случай, если head успел уйти дальше
uv run python seed/reset_demo_passwords.py # ОБЯЗАТЕЛЬНО, см. «Пароли» ниже
```

Если база не пустая — сначала пересоздайте её:

```bash
docker exec vektor-backend-db-1 psql -U vektor -d postgres \
  -c "DROP DATABASE vektor;" -c "CREATE DATABASE vektor;"
```

## Пароли — обязательный шаг


после восстановления запустите `seed/reset_demo_passwords.py` — он
проставит всем живым учёткам ваш локальный `BULK_DEFAULT_PASSWORD`. Скрипт
идемпотентен. Служебные респонденты (`is_placeholder = true`) пропускаются: они
не логинятся в принципе. **Не путать с админом**: `reset_demo_passwords.py`
задевает и его (грабля из CLAUDE.md, Этап 6) — если нужен именно
`.env`-пароль админа, пересчитать его хеш отдельно.

