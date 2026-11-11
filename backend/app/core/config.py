from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def to_sqlalchemy_url(url: str) -> str:
    """Accept postgres://, postgresql:// and postgresql+psycopg:// and return the psycopg3 dialect URL."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/figsa"
    migration_database_url: str = ""
    jwt_secret: str = "change-me"
    jwt_hours: int = 12
    allowed_origins: str = "http://localhost:5173"
    tz: str = "America/Guatemala"
    default_exchange_rate: float = 7.70
    max_upload_mb: int = 16

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_service_account_json: str = ""

    @property
    def sqlalchemy_url(self) -> str:
        return to_sqlalchemy_url(self.database_url)

    @property
    def migration_url(self) -> str:
        return to_sqlalchemy_url(self.migration_database_url or self.database_url)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
