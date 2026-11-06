"""Real database/API smoke check; use only a disposable configured database."""

import asyncio

from fastapi.testclient import TestClient

from axtor.core.config import Settings
from axtor.main import create_app
from axtor.persistence.database import Database


async def probe() -> None:
    database = Database(Settings())
    try:
        await database.check()
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(probe())
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
