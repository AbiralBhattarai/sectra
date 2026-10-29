from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.adapters.input.rest.router import build_router
from src.config.container import build_container
from src.config.logging_config import configure_logging
from src.config.settings import Settings, get_settings
from src.domain.exceptions import AppValidationException, NotFoundException


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(title="Sectra", lifespan=lifespan)
    app.include_router(build_router())

    @app.exception_handler(NotFoundException)
    async def not_found(_: Request, exc: NotFoundException) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AppValidationException)
    async def invalid(_: Request, exc: AppValidationException) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return app
