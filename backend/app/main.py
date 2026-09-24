from fastapi import APIRouter, Depends, FastAPI

from app.auth import require_same_origin
from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.routers import auth, experiences, job_postings
from app.sentry_setup import init_sentry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    init_sentry(settings.sentry_dsn, settings.environment)

    is_production = settings.environment == "production"
    app = FastAPI(
        title="JDive API",
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # 상태를 바꾸는 요청은 모두 Origin 검증을 거친다(CSRF).
    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_same_origin)])
    api.include_router(auth.router)
    api.include_router(experiences.router)
    api.include_router(job_postings.router)
    app.include_router(api)

    return app


app = create_app()
