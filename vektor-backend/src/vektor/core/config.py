from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения. Читаются из окружения / .env.

    На Этапе 0 нужны только базовые поля. database_url и redis_url
    уже объявлены, но реально подключим их в Этапе 1 (core).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret_key: str = "dev-token-need-change"
    access_token_expire_minutes: int = 60 * 24

    app_name: str = "Платформа Вектор API"
    app_version: str = "0.1.0"
    environment: str = "local"

    # Заполним и начнём использовать в Этапе 1
    database_url: str = "postgresql+asyncpg://vektor:vektor@localhost:5432/vektor"
    redis_url: str = "redis://localhost:6379/0"

    admin_email: str | None = None
    admin_password: str | None = None

    # ВРЕМЕННО (Этап 3.7): единый пароль для всех, кого заводим массово.
    # Позже заменится авто-генерацией + рассылкой. Держим в настройках,
    # чтобы не хардкодить в коде и переопределять через .env.
    bulk_default_password: str = "somepassword_to_copy"

    log_level: str = "INFO"

    # SQL-эхо теперь ВЫКЛЮЧЕНО по умолчанию (раньше включалось само при
    # environment=local). Причина: появился настоящий access-лог, а эхо
    # печатает каждый SELECT и топит его — на одном запросе к результатам
    # это десятки строк. Включается через DB_ECHO=true, когда нужно
    # разглядывать запросы.
    db_echo: bool = False

    # Разрешённые Origin для CORS, через запятую.
    #
    # В разработке НЕ НУЖНО: фронт ходит через прокси Vite (/api → :8000),
    # и для браузера это один origin — см. vektor-frontend/vite.config.ts.
    # Нужно там, где фронт отдаётся с другого домена, чем API. Пусто —
    # middleware не подключается вовсе, а не «разрешить всё».
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Ограничение частоты — только на вход и регистрацию (перебор паролей и
    # массовое создание учёток). Пороги с запасом: живой человек, ошибившийся
    # паролем несколько раз подряд, под лимит попасть не должен.
    # Выключается целиком в тестах: они делают десятки логинов подряд и
    # пробивают любой разумный порог. Проверяется отдельным test_rate_limit.py,
    # который включает флаг обратно.
    rate_limit_enabled: bool = True

    login_rate_limit: int = 10
    login_rate_window_seconds: int = 60
    register_rate_limit: int = 5
    register_rate_window_seconds: int = 300


settings = Settings()
