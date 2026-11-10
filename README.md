# Axtor

Independent API-first AI Action Governance Engine (`ywptr/axtor`). Phase 0 provides
application infrastructure only. See [architecture](docs/ARCHITECTURE.md) and
[repository instructions](AGENTS.md) for ownership boundaries.

## Local development

Requires Docker and Docker Compose **2.24.4+** (overlay uses `!override` and
`!reset`). Python 3.12+ (VM target: 3.13) is needed for host-side checks.

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD to a unique URL-safe local password.
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml up --build -d
# Explicit operator action; never run automatically at startup or reload:
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml exec api alembic upgrade head
```

API: <http://127.0.0.1:8013>. Development docs:
<http://127.0.0.1:8013/docs>; schema: <http://127.0.0.1:8013/openapi.json>.
Host `127.0.0.1:8013` maps to container port **8000**. Port **5183** is reserved
for a future Axtor web/admin frontend; nothing in this repository listens on it.
There is no Payload CMS, Next.js, or admin frontend in this engine.

The explicit development overlay bind-mounts only `./src` at `/app/src` read-only.
`PYTHONPATH=/app/src` makes Uvicorn import mounted code instead of the installed
package copy. Native `--reload --reload-dir /app/src` watches Python source using
Uvicorn's polling fallback; no watcher dependency is required. Editing host Python
files restarts the worker without rebuilding. Dependencies remain installed under
`/usr/local/lib`, outside the mount. A host `.venv` is never mounted.

Rebuild after dependency/constraints, packaging or Dockerfile changes using the
startup command above. Restart/recreate after environment or Compose changes.
Migration files are copied into the image, so rebuild after changing them, then
run Alembic explicitly. README/docs changes alone need no running-service rebuild.

```sh
curl -i http://127.0.0.1:8013/health
curl -i http://127.0.0.1:8013/ready
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml logs -f api
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml down
```

`/health` requires no database; `/ready` returns 503 on a connectivity failure.
Readiness checks connectivity, not migration currency. No CORS origins are allowed
by default. Errors use a safe envelope and responses include `X-Correlation-ID`.

### Database safety and production separation

The dev overlay removes **all** database host port publications. PostgreSQL is
reachable only by the API at `db:5432` on a project-scoped internal database
network. The API also joins the project's default network for its published port.
Other suite applications are not attached to either network. No external/shared
network or database is referenced. The project-scoped `postgres_data` volume is
persistent; `down` preserves it. Never use `down -v` for data you want to retain.
Changing POSTGRES_PASSWORD does not rotate credentials in an existing volume.

Use a URL-safe POSTGRES_PASSWORD in `.env` (gitignored). The API's Compose URL is
constructed from it; the standalone AXTOR_DATABASE_URL example uses the internal
hostname and is not a host PostgreSQL endpoint. Host-side tests mock database
boundaries. Do not connect these commands to suite or production databases.
For SQL inspection, use the isolated container:

```sh
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml exec db psql -U axtor -d axtor
```

`Dockerfile` and base `compose.yaml` remain unchanged. The base alone retains its
Phase 0 mappings (8000 API, 5432 DB), and is **not** the suite development command.
Always pass both files for development. Never load `compose.dev.yaml` in
production. The Dockerfile's command has no source mount or reload. Production
configuration should set AXTOR_ENVIRONMENT=production to disable docs/OpenAPI;
Phase 0's base Compose is a local baseline, not a complete production deployment.

### Host-side checks

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -c constraints.txt -e '.[dev]'
ruff check .
ruff format --check .
mypy
pytest
```

### Disposable migration validation

Stop the development API first so that port 8013 is free. Use a distinct project
and its own volume; never point this at existing databases:

```sh
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml up --build -d --wait
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml exec api alembic upgrade head
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml exec api alembic current
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml exec api alembic check
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml exec api alembic downgrade base
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml exec api alembic upgrade head
curl -f http://127.0.0.1:8013/health
curl -f http://127.0.0.1:8013/ready
docker compose -p axtor-net-check -f compose.yaml -f compose.dev.yaml down -v
```

The last command deletes only the disposable project's database volume. CI also
runs the migration cycle against a fresh PostgreSQL service. See
[networking validation](docs/DEV_NETWORK_REPORT.md) for actual verification and
operator-confirmed live acceptance results.

`constraints.txt` records the tested dependency versions; update it deliberately
and rerun checks when upgrading. It is a version snapshot, not a hash-verified
lock. The Docker build installs runtime dependencies only.
