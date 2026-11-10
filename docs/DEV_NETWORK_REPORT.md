# Development networking validation — closure 2026-11-10

**Live acceptance: PASS**, confirmed by the operator in the regular SSH session
on `5480-deb13`. Earlier command results below retain historical context.

Repository `ywptr/axtor`, VM `5480-deb13`, initial HEAD `e95ec4f` (`Created
foundations`), initial Git status clean. Read-only inspection completed before
editing: Dockerfile, Compose, app/configuration/database modules, Alembic,
packaging, CI, README, architecture and repository instructions were reviewed.

## Architecture before and after

| Concern | Before: base Compose | After: explicit development overlay |
| --- | --- | --- |
| Host API | `127.0.0.1:8000` | `127.0.0.1:8013` |
| Container API | `0.0.0.0:8000` | unchanged |
| Source | image-installed package | read-only `./src:/app/src`, imported via `PYTHONPATH=/app/src` |
| Reload | none | native Uvicorn `--reload --reload-dir /app/src` |
| Dependencies | image site-packages | unchanged, outside mounted source |
| PostgreSQL publication | `127.0.0.1:5432:5432` | none |
| DB network | project default | project-scoped internal `database` network |
| API networks | project default | project default plus internal database network |
| Migrations | explicit operator command | unchanged, never invoked by reload/startup |
| Future frontend | absent | absent, port 5183 reserved |

`compose.dev.yaml` uses `!override` for API ports, preventing port 8000 from also
being published, and `!reset []` to remove DB publications. Compose 2.24.4+ is
required. No shared/external suite network is referenced. The API uses the local
Compose DB service, not any existing VM, suite, production or Neon database.

## Files changed

- Added `compose.dev.yaml`: explicit development-only networking, mount and command.
- Updated `.env.example`: internal database hostname and URL-safe password guidance.
- Updated `README.md`: exact suite startup, migration, reload, rebuild, database
  safety, frontend reservation, and disposable validation commands.
- Updated `docs/ARCHITECTURE.md`: development overlay boundaries.
- Added this report, updated the Phase 0 closure report, and added the manual
  infrastructure acceptance script.

Dockerfile, base `compose.yaml`, app source, migrations, dependencies and CI are
unchanged, confirmed with `git diff --exit-code HEAD -- Dockerfile compose.yaml
src alembic pyproject.toml constraints.txt .github/workflows/ci.yaml` (exit 0).
No governance changes, frontend or other-application changes. Closure authorizes
one local infrastructure/documentation commit; no push is performed.
The baseline Compose is a local Phase 0 baseline, not a production deployment.
The production image command still has no reload; production docs-off behavior
continues to be covered by the existing tests.

## Startup and actual resolved mappings

```sh
cp .env.example .env
# Set a unique URL-safe POSTGRES_PASSWORD in the gitignored .env.
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml up --build -d
docker compose -p axtor-dev -f compose.yaml -f compose.dev.yaml exec api alembic upgrade head
```

Resolved mappings: `127.0.0.1:8013 -> api:8000/tcp`; database ports `[]`;
no port 5183 listener. API URL `http://127.0.0.1:8013`, docs `/docs`, schema
`/openapi.json`. PostgreSQL stays at `db:5432` inside the project. The dev project's
networks/volume are `axtor-dev_default`, `axtor-dev_database` (internal), and
`axtor-dev_postgres_data`. The disposable validation project resolves to the same
structure under `axtor-net-check_*`.

Editing Python source reloads without rebuilding. Dependencies, packaging,
Dockerfile and copied migrations require rebuilding. Compose/environment changes
require recreation. Migrations always require an explicit Alembic command.

## Commands and evidence

- `docker compose version`: **v5.7.0**. Docker client **29.9.3**. Server version
  could not be read because socket access is denied.
- `POSTGRES_PASSWORD=validation-only docker compose -p axtor-net-check -f
  compose.yaml -f compose.dev.yaml config --format json`: exit **0**. Python
  assertions verified exact API publication, no DB ports, DB-only internal
  network, read-only source mount, PYTHONPATH, native reload, and no Alembic in
  startup. The placeholder was used only for configuration validation/startup
  attempts; no environment file or database was created.
- `ss -ltn` outside sandbox: 8013 and 5183 had no listeners. Existing suite
  services occupy 8011/8012 and 5180/5181/5182; they were not changed. Existing
  PostgreSQL listeners on host/bridge port 5432 were not contacted.
- `.venv/bin/ruff check .`: **All checks passed!**, exit **0**.
- `.venv/bin/ruff format --check .`: **19 files already formatted**, exit **0**.
- `.venv/bin/mypy`: **Success: no issues found in 14 source files**, exit **0**.
- `.venv/bin/pytest -q` outside sandbox: **20 passed, 1 warning in 1.57s**, exit
  **0**. The existing upstream warning deprecates Starlette's HTTPX TestClient
  support; no new warnings were introduced.
- `git diff --check`: no output, exit **0**.

### Live host reload check

A temporary subprocess used the installed project dependencies and this command:

```sh
PYTHONPATH="$PWD/src" \
AXTOR_ENVIRONMENT=development \
AXTOR_DATABASE_URL=postgresql+asyncpg://validation:validation@127.0.0.1:1/validation \
PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/python -m uvicorn axtor.main:create_app --factory \
  --host 127.0.0.1 --port 8013 --no-proxy-headers --reload --reload-dir "$PWD/src"
```

The automated urllib probe exited **0** and observed:

```text
Port 8013: available before check
Port 5183: available before check
/health: HTTP 200
/ready: HTTP 503
/docs: HTTP 200
/openapi.json: HTTP 200
Temporary source title visible in OpenAPI without rebuild: PASS
Original source and OpenAPI title restored: PASS
Worker PIDs: 808290, 808325, 808365
INFO: Started reloader process [808281] using StatReload
INFO: Started server process [808290]
WARNING: StatReload detected changes in 'src/axtor/main.py'. Reloading...
INFO: Started server process [808325]
WARNING: StatReload detected changes in 'src/axtor/main.py'. Reloading...
INFO: Started server process [808365]
Temporary server stopped; ports 8013/5183 free
```

The harmless temporary edit changed the FastAPI title to `Axtor reload
verification`. OpenAPI showed it after reload and showed `Axtor` after restoring
original bytes. Cleanup ran in a finally block; app source has no residual diff.
Local details are retained in gitignored `network-verification.log`. This proves
native reload/import behavior on the host; it does **not** prove a Docker bind
mount's live behavior. Database-unavailable readiness was tested deliberately
against loopback port 1, without accessing an existing PostgreSQL instance.

### Final live container acceptance

The operator confirmed successful Phase 0 acceptance in the regular SSH session:

- Both development containers healthy; API at `127.0.0.1:8013`.
- PostgreSQL has no published host ports.
- Read-only source bind is correct.
- Native Uvicorn reload works inside the running API container.
- Temporary source modification restored byte-for-byte.
- `/health`, `/ready`, `/openapi.json` each return HTTP 200 after reload.
- Database schema and migration revision unchanged; no migrations executed.

Evidence is the operator's acceptance summary, not a raw transcript captured by
Codex. These live results supersede the earlier host-only reload limitation and
Docker access blocker. The declared persistent volume is
`axtor-dev_postgres_data`; the manual script verifies its live mount, but the
operator's summary does not separately quote the volume inspection output.

Manual reproduction, from regular SSH in this repository:

```sh
bash scripts/phase0_acceptance.sh axtor-dev
```

This script inspects the live source mount, PostgreSQL publications and volume,
Uvicorn command, Alembic current/heads/history, and schema before/after reload.
It makes no migration or container lifecycle changes. Source restoration runs
on failures and catchable signals; an exclusive backup permits manual recovery
if interrupted by SIGKILL or host failure. Avoid concurrent source edits.

### Execution identity and closure

The SSH account is configured for Docker GID 989, but Codex's process lacked
that supplementary group. Its namespace maps contained only `1000 0 1`, and the
socket appeared as `65534:65534`. No permissions, membership or daemon settings
were changed. This execution limitation is no longer an acceptance blocker
because live checks passed in the regular SSH environment.

Closure repeats Git whitespace checks, tests, Ruff, formatting and mypy, and
checks staged scope for secrets and temporary files. No application functionality
or database state is changed. The existing TestClient deprecation warning remains.
No Phase 1 work or push is included.
