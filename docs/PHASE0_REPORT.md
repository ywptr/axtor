# Phase 0 delivery and verification

## Scope and initial state

Repository: `ywptr/axtor`, branch `main`, HEAD `4fb898c` (`Initial commit`).
Initial Git status was clean. Only `.gitignore`, `LICENSE`, and `README.md` were
tracked; an existing `.venv` was preserved. No applicable AGENTS.md existed.
No commits or pushes were created, no other applications were changed, and no
production or Neon databases were accessed. Phase 1 work has not begun.

## Files

Modified: `.gitignore`, `README.md`.

Created:

- `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/PHASE0_REPORT.md`
- `pyproject.toml`, `constraints.txt`, `.env.example`, `.dockerignore`
- `Dockerfile`, `compose.yaml`, `.github/workflows/ci.yaml`
- `src/axtor/main.py`, `src/axtor/core/config.py`, `src/axtor/core/http.py`
- `src/axtor/persistence/database.py`, `src/axtor/schemas/responses.py`
- Package `__init__.py` files in `src/axtor`, `api`, `core`, `persistence`, `schemas`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`,
  `alembic/versions/0001_baseline.py`
- `tests/test_foundation.py`, `scripts/verify_database.py`

Local generated artifacts (virtual environment, caches and the failed initial
`dependency-install.log`) are ignored, not deliverable source.

## Decisions

Python uses a src package and standard pyproject packaging. Application factory
configuration is validated before serving. Async SQLAlchemy has bounded pools,
pre-ping, connection/acquisition/query deadlines and shutdown disposal. The
session factory does not commit implicitly. Liveness is independent of the DB;
readiness probes it without exposing exception details. Correlation IDs are
validated observability metadata. There is no CORS allowlist by default, and docs
are disabled in production. Compose publishes ports on loopback; the API container
runs without root. Migrations are explicit and the baseline creates no domain
schema. Ownership, canonical UUID isolation, distinct identity concepts and
proposal/adjudication/authorization/execution boundaries are documented in
AGENTS.md and ARCHITECTURE.md.

## Versions

VM: Python **3.13.5**, virtualenv pip **25.1.1**. System Python has no pip module.
Docker, Docker Compose, PostgreSQL client/server and uv are absent. Ruff and Mypy
were absent before installing the dev extra. PostgreSQL 17 and Python 3.13 are the
container targets; those images have not been built or started locally.

Installed principal dependencies:

| Dependency | Version |
| --- | --- |
| FastAPI | 0.162.0 |
| Pydantic | 2.14.3 |
| pydantic-settings | 2.16.2 |
| SQLAlchemy | 2.1.8 |
| asyncpg | 0.32.0 |
| Alembic | 1.20.1 |
| Uvicorn | 0.54.0 |
| Pytest | 9.2.0 |
| HTTPX | 0.28.1 |
| Ruff | 0.17.4 |
| Mypy | 1.20.2 |
| Starlette | 1.10.0 |

All resolved versions are in `constraints.txt`, used by documented installs,
CI and Docker. This is a version snapshot, not a hash-verified lock; build-system
requirements and container tags are not digest pinned.

## Exact command results

Commands ran from `/home/user/src/axtor`. The initial sandboxed
`.venv/bin/pip install -e '.[dev]' > dependency-install.log 2>&1` exited **1**
because DNS/network restrictions prevented fetching hatchling. The approved
outside-sandbox retry `.venv/bin/pip install -e '.[dev]'` exited **0**, built
`axtor-0.1.0` and installed all runtime/dev dependencies. Downloads were slow.

Initial `.venv/bin/ruff check . --fix` found an import issue (fixed automatically)
and one E501 long line. `.venv/bin/ruff format .` reformatted four files and
resolved the long line. Final results:

```text
$ .venv/bin/ruff check .
All checks passed!
exit 0

$ .venv/bin/ruff format --check .
18 files already formatted
exit 0

$ .venv/bin/mypy
Success: no issues found in 14 source files
exit 0

$ .venv/bin/pip check
No broken requirements found.
exit 0

$ .venv/bin/pytest -q
20 passed, 1 warning in 1.13s
exit 0

$ python3 -m compileall -q src tests alembic scripts
(no output), exit 0

$ git diff --check
(no output), exit 0
```

Sandboxed Pytest was interrupted (exit 130) after hanging at TestClient startup.
A diagnostic `.venv/bin/pytest -vv -o faulthandler_timeout=15` also hung and was
interrupted. Its trace showed Starlette/AnyIO waiting on cross-thread event-loop
startup. The approved outside-sandbox test run passed all 20 cases. The one
warning is `StarletteDeprecationWarning`: HTTPX support in Starlette TestClient
is deprecated in favor of httpx2. HTTPX remains the requested Phase 0 test client;
this warning is not suppressed.

Tests cover initialization and docs, liveness independent of DB, readiness
success/failure, database SELECT success/failure and deadline, validation of
required/environment settings, HTTP/validation/unhandled errors, correlation ID
acceptance/replacement/propagation and engine cleanup. Database successes in the
unit suite are mocked; they do not establish PostgreSQL compatibility.

```text
$ AXTOR_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:1/test .venv/bin/alembic upgrade head --sql
BEGIN;
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
-- Running upgrade  -> 0001
INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;
COMMIT;
exit 0

$ docker compose -p axtor-phase0-check build
/bin/bash: docker: command not found
exit 127

$ docker compose -p axtor-phase0-check up -d
/bin/bash: docker: command not found
exit 127

$ psql --version
/bin/bash: psql: command not found
exit 127
```

A temporary Uvicorn server was run outside the sandbox on `127.0.0.1:18763` with
`AXTOR_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:1/test`. It was started
with `.venv/bin/uvicorn axtor.main:create_app --factory --host 127.0.0.1 --port 18763`,
probed with Python urllib, then terminated. The smoke command exited **0**:

```text
/health 200 {"status":"ok"}
/ready 503 {"error":{"code":"database_unavailable","message":"Service is not ready","correlation_id":"bed5dad2-ad3e-4462-9324-6e5b3df34bae"}}
```

The smoke check asserted readiness 503 and a correlation header. No database was
listening at the configured port. No background server was left running.

## Unverified work and limitations

Live migration upgrade/downgrade/check against disposable PostgreSQL, successful
real PostgreSQL readiness, and Compose build/startup could not run because the
VM lacks Docker and PostgreSQL. Installing system packages would change files
outside the authorized repository. README gives exact disposable verification
commands. CI provisions fresh PostgreSQL, runs migration upgrade/check/downgrade/
upgrade and calls `scripts/verify_database.py` for real connectivity and API
health/readiness. That workflow has been authored but has not run on GitHub.

Phase 0 is implemented, but its full infrastructure acceptance is pending those
live checks. Offline SQL generation is not a substitute for migration execution.
Production deployment still needs TLS, secret injection, deployment-specific
network and database security, and sanitized structured diagnostics. Readiness
tests connectivity only, not migration currency. No authentication or domain
endpoints exist. Base image digests and dependency hashes remain unpinned.

## Recommended Phase 1 sequence (not implemented)

1. Complete disposable PostgreSQL and Docker acceptance checks first.
2. Define `/v1` API contracts and distinct proposal/adjudication/authorization/
   execution schemas, with calling service, initiating actor, canonical tenant
   UUID and delegation chain represented separately.
3. Agree IS authentication and Nexus tenant/membership/entitlement contracts as
   cross-application handoffs; do not change their repositories here.
4. Design canonical UUID isolation and negative isolation tests before adding
   tenant-owned persistence. Introduce reviewed explicit migrations.
5. Implement and test the first governance use case only after identity,
   ownership, policy and consumer-enforcement contracts are agreed.
