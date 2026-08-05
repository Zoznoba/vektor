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


settings = Settings()
