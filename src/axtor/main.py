import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from axtor.core.config import Settings
from axtor.core.http import CorrelationMiddleware
from axtor.persistence.database import Database
from axtor.schemas.responses import ErrorResponse, StatusResponse

logger = logging.getLogger(__name__)


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    correlation_id = request.state.correlation_id
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "correlation_id": correlation_id}},
        headers={"X-Correlation-ID": correlation_id},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    database = Database(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await database.close()

    app = FastAPI(
        title="Axtor",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.environment != "production" else None,
    )
    app.state.database = database
    app.add_middleware(CorrelationMiddleware)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, exc.status_code, "http_error", "Request could not be completed")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, 422, "validation_error", "Request validation failed")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled request error correlation_id=%s", request.state.correlation_id)
        return error(request, 500, "internal_error", "Internal server error")

    @app.get("/health", response_model=StatusResponse)
    async def health() -> StatusResponse:
        return StatusResponse(status="ok")

    @app.get("/ready", response_model=StatusResponse, responses={503: {"model": ErrorResponse}})
    async def ready(request: Request) -> StatusResponse | JSONResponse:
        try:
            await database.check()
        except Exception:
            return error(request, 503, "database_unavailable", "Service is not ready")
        return StatusResponse(status="ready")

    return app
