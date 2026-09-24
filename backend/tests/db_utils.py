from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
# docker compose up -d db 로 띄운 로컬 DB. CI 는 TEST_DATABASE_URL 로 덮어쓴다.
# localhost 는 Windows 에서 IPv6(::1)를 먼저 시도해 접속마다 수 초가 걸리므로 127.0.0.1 을 쓴다.
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://jdive:jdive_dev@127.0.0.1:5433/jdive_test"
ALL_TABLES = "users, sessions, experiences, job_postings, analysis_runs"


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False  # 앱·pytest 의 로깅 설정을 덮어쓰지 않는다
    return config


def ensure_database(database_url: str, suffix: str = "") -> str:
    """테스트용 DB 가 없으면 만들고, 그 DB 의 접속 URL 을 돌려준다."""
    url = make_url(database_url)
    name = f"{url.database}{suffix}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if not exists:
                # 이름은 우리 설정에서만 오고, 식별자이므로 따옴표로 감싼다.
                conn.execute(text(f'CREATE DATABASE "{name}"'))  # noqa: S608
    finally:
        admin.dispose()
    return url.set(database=name).render_as_string(hide_password=False)
