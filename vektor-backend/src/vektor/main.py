from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from vektor.core.config import settings
from vektor.core.database import async_session_factory, engine
from vektor.core.errors import register_error_handlers
from vektor.core.logging import setup_logging
from vektor.core.middleware import RequestContextMiddleware
from vektor.modules.assessments.router import assessment_router
from vektor.modules.assessments.router import router as assessments_router
from vektor.modules.auth.router import router as auth_router
from vektor.modules.classes.router import router as classes_router
from vektor.modules.competencies.router import router as competency_router
from vektor.modules.results.router import router as results_router
from vektor.modules.users.bootstrap import ensure_admin_exists
from vektor.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session_factory() as session:
        await ensure_admin_exists(session)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

    # Доменные исключения переводятся в HTTP здесь, а не в каждом роутере:
    # см. core/errors.py — там же про единый формат тела ответа.
    register_error_handlers(app)

    app.add_middleware(RequestContextMiddleware)

    # CORS подключается ТОЛЬКО при непустом списке origin'ов. В разработке он
    # не нужен: фронт ходит через прокси Vite (/api → :8000), и для браузера
    # это один origin. Пустая настройка означает «middleware нет», а не
    # «разрешить всё» — иначе забытый .env открыл бы API любому сайту.
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(
                status_code=503, content={"status": "error", "database": "unavailable"}
            )
        return {"status": "ok"}

    return app


app = create_app()
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(competency_router)
app.include_router(classes_router)
app.include_router(assessments_router)
app.include_router(assessment_router)
app.include_router(results_router)
