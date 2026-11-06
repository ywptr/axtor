import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axtor.core.config import Settings
from axtor.main import create_app
from axtor.persistence.database import Database

URL = "postgresql+asyncpg://test:test@127.0.0.1:1/test"


@pytest.fixture
def app() -> Iterator[FastAPI]:
    application = create_app(Settings(_env_file=None, database_url=URL))
    yield application


def test_initialization(app: FastAPI) -> None:
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert "/health" in client.get("/openapi.json").json()["paths"]


def test_health_does_not_check_database(app: FastAPI) -> None:
    app.state.database.check = AsyncMock(side_effect=AssertionError("must not connect"))
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    app.state.database.check.assert_not_called()


@pytest.mark.parametrize("failure", [False, True])
def test_readiness(app: FastAPI, failure: bool) -> None:
    app.state.database.check = AsyncMock(
        side_effect=RuntimeError("private credentials") if failure else None
    )
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == (503 if failure else 200)
    assert "private credentials" not in response.text
    if failure:
        assert response.json()["error"]["code"] == "database_unavailable"
    app.state.database.check.assert_awaited_once()


@pytest.mark.parametrize("supplied", [None, "caller-123", "bad id", "x" * 129])
def test_correlation(app: FastAPI, supplied: str | None) -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Correlation-ID": supplied} if supplied else {})
    value = response.headers["X-Correlation-ID"]
    if supplied == "caller-123":
        assert value == supplied
    else:
        UUID(value)


@pytest.mark.parametrize("path,status", [("/missing", 404), ("/health", 405)])
def test_http_errors(app: FastAPI, path: str, status: int) -> None:
    with TestClient(app) as client:
        response = client.post(path) if status == 405 else client.get(path)
    assert response.status_code == status
    assert response.json()["error"]["correlation_id"] == response.headers["X-Correlation-ID"]


def test_unhandled_and_validation_errors(app: FastAPI) -> None:
    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("secret")

    @app.get("/validated")
    async def validated(count: int) -> int:
        return count

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/crash", headers={"X-Correlation-ID": "trace-1"})
        assert response.status_code == 500
        assert "secret" not in response.text
        assert response.headers["X-Correlation-ID"] == "trace-1"
        response = client.get("/validated?count=secret")
        assert response.status_code == 422
        assert "secret" not in response.text


@pytest.mark.parametrize("value", ["sqlite:///test.db", "postgresql://x:y@localhost/db", "bad"])
def test_invalid_database_url(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=value)


def test_missing_and_invalid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AXTOR_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=URL, db_pool_size=0)
    monkeypatch.setenv("AXTOR_DATABASE_URL", URL)
    assert str(Settings(_env_file=None).database_url) == URL


def test_production_docs_disabled() -> None:
    app = create_app(Settings(_env_file=None, database_url=URL, environment="production"))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert (
            "access-control-allow-origin"
            not in client.get("/health", headers={"Origin": "https://example.com"}).headers
        )


@pytest.mark.parametrize("failure", [False, True])
def test_database_probe(failure: bool) -> None:
    async def scenario() -> None:
        database = Database(Settings(_env_file=None, database_url=URL))
        connection = AsyncMock()
        connection.execute.side_effect = RuntimeError("offline") if failure else None
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=connection)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch("sqlalchemy.ext.asyncio.AsyncEngine.connect", return_value=context):
            if failure:
                with pytest.raises(RuntimeError):
                    await database.check()
            else:
                await database.check()
            assert str(connection.execute.call_args.args[0]) == "SELECT 1"
        await database.close()

    asyncio.run(scenario())


def test_database_deadline() -> None:
    async def scenario() -> None:
        database = Database(Settings(_env_file=None, database_url=URL, db_timeout_seconds=0.01))
        context = MagicMock()
        context.__aenter__ = AsyncMock(side_effect=lambda: None)

        async def slow() -> None:
            await asyncio.sleep(1)

        context.__aenter__.side_effect = slow
        context.__aexit__ = AsyncMock(return_value=False)
        try:
            with patch("sqlalchemy.ext.asyncio.AsyncEngine.connect", return_value=context):
                with pytest.raises(TimeoutError):
                    await database.check()
        finally:
            await database.close()

    asyncio.run(scenario())


def test_shutdown_disposes_engine(app: FastAPI) -> None:
    app.state.database.close = AsyncMock()
    with TestClient(app):
        pass
    app.state.database.close.assert_awaited_once()
