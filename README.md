# Axtor

Independent API-first AI Action Governance Engine (`ywptr/axtor`). Phase 0 provides
application infrastructure only. See [architecture](docs/ARCHITECTURE.md) and
[repository instructions](AGENTS.md) for ownership boundaries.

## Local development

Requires Python 3.12+ (VM target: 3.13), Docker and Docker Compose v2.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -c constraints.txt -e '.[dev]'
cp .env.example .env
# Set a local password in both values; URL-encode it in the database URL.
docker compose up -d db
alembic upgrade head
uvicorn axtor.main:create_app --factory --host 127.0.0.1 --port 8000
```

Alternatively, `docker compose up --build -d`, then explicitly run
`docker compose run --rm api alembic upgrade head`. Startup never runs migrations.
Compose is for local development; it requires `POSTGRES_PASSWORD` in `.env` and
uses the container hostname `db` for the API database connection. Use a URL-safe
local password, or supply an appropriately encoded connection URL in your own
deployment configuration. Never point these commands at a production database.

```sh
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/ready
ruff check .
ruff format --check .
mypy
pytest
```

Development docs: <http://127.0.0.1:8000/docs>. `/health` needs no database;
`/ready` returns 503 when the bounded connectivity probe fails. Errors use
`{"error":{"code":"...","message":"...","correlation_id":"..."}}` and
responses include `X-Correlation-ID`. No CORS origins are allowed by default.
Set `AXTOR_ENVIRONMENT=production` to disable interactive docs and OpenAPI.
`AXTOR_DATABASE_URL` is required; pool limits and timeout can be set with
`AXTOR_DB_POOL_SIZE`, `AXTOR_DB_MAX_OVERFLOW`, `AXTOR_DB_TIMEOUT_SECONDS`.

## Disposable migration validation

Use a distinct Compose project and database volume, not an existing database:

```sh
docker compose -p axtor-phase0-check up --build -d
# With no other local stack occupying ports 5432/8000:
docker compose -p axtor-phase0-check run --rm api alembic upgrade head
docker compose -p axtor-phase0-check run --rm api alembic current
docker compose -p axtor-phase0-check run --rm api alembic check
docker compose -p axtor-phase0-check run --rm api alembic downgrade base
docker compose -p axtor-phase0-check run --rm api alembic upgrade head
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
docker compose -p axtor-phase0-check down -v
```

The final command deletes only that disposable project's database volume. CI
runs the same migration cycle against a fresh PostgreSQL service. Unit tests mock
database boundaries; CI also exercises real connectivity and API probes.

`constraints.txt` records the tested dependency versions; update it deliberately
and rerun checks when upgrading. It is a version snapshot, not a hash-verified
lock. The Docker build installs runtime dependencies only.
