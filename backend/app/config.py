from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(와 저장소 루트의 .env)에서 읽는 설정. 시크릿에는 기본값을 두지 않는다."""

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: str = "development"
    # 브라우저가 접속하는 공개 URL. Google Redirect URI 는 이 값에서 만든다.
    public_base_url: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://jdive:jdive_dev@localhost:5433/jdive"
    session_secret: str = ""
    session_ttl_days: int = 14
    google_client_id: str = ""
    google_client_secret: str = ""
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
