# Phase 0 delivery and verification

**Closure: PASS.** Live development acceptance was confirmed by the operator in
the regular SSH session on `5480-deb13`. The initial delivery sections below are
historical; the final acceptance section records the current status.

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


## Final runtime acceptance and closure — 2026-11-10

**PASS**, based on operator-confirmed live acceptance in the regular SSH
environment on `5480-deb13`. Evidence was supplied in the closure request;
a raw SSH transcript and exact live revision value were not supplied. These
results supersede the earlier Docker-access blocker and infrastructure-pending
statements. Codex did not independently repeat the Docker checks.

| Acceptance criterion | Result and evidence |
| --- | --- |
| Development containers | PASS — both API and PostgreSQL healthy. |
| API publication | PASS — API available at 127.0.0.1:8013. |
| Source mount | PASS — correct read-only source bind verified live. |
| Uvicorn native reload | PASS — temporary source modification observed through container reload. |
| Restoration | PASS — original source restored byte-for-byte. |
| HTTP probes after reload | PASS — /health, /ready and /openapi.json return HTTP 200. |
| PostgreSQL host isolation | PASS — no published host ports. |
| Schema and migration revision | PASS — unchanged across acceptance; no migrations executed. |
| Startup migrations | PASS — source/configuration launch only Uvicorn; live reload left schema and revision unchanged. |

Expected migration head is `0001`, an empty infrastructure baseline with no
application tables. An unchanged live revision does not imply that migrations
were applied. No upgrade, downgrade, stamp, or database mutation was performed
as part of acceptance or closure. No schema changes are being shipped, so a
new disposable migration cycle was not run during closure.

The development overlay declares the project-scoped `postgres_data` volume at
`/var/lib/postgresql/data`. The manual acceptance script checks the live volume
name as well as mount, ports, revision, schema and reload. The operator's summary
does not separately quote the volume inspection output.

### Execution environment diagnosis

The regular SSH user has Docker group membership (GID 989). Codex's effective
process groups contained only 1000 and 65534; its namespace UID/GID maps contained
`1000 0 1`, and the socket appeared as UID/GID 65534. This is a Codex execution
environment limitation, not an outstanding application acceptance failure. No
socket permissions, group membership, daemon configuration or application code
were changed to work around it.

### Closure scope and validation

Included Phase 0 infrastructure: `compose.dev.yaml`, `.env.example`, development
instructions in `README.md` and `docs/ARCHITECTURE.md`, both validation reports,
and `scripts/phase0_acceptance.sh`. Existing application source, migrations,
Dockerfile, base Compose, dependencies and CI remain unchanged.

The manual script uses read-only Docker inspection and schema dumps; its only
source edit is a temporary OpenAPI title restored on exceptions and catchable
INT/TERM/HUP. An exclusive source backup supports recovery after uncatchable
interruption. It never runs migrations or container lifecycle operations.

Closure checks: `git diff --check`, `.venv/bin/ruff check .`,
`.venv/bin/ruff format --check .`, `.venv/bin/mypy`, `.venv/bin/pytest -q`,
shell syntax and embedded Python syntax validation all passed. Ruff reported
“All checks passed!”, formatting reported 19 files already formatted, mypy
reported no issues in 14 source files, and pytest reported 20 passed, 1 warning
in 1.27s. The existing Starlette TestClient HTTPX
deprecation warning remains. No secrets or temporary backups are included.

One local Phase 0 closure commit is authorized; no push is authorized or performed.
Phase 1, production rollout, domain logic and cross-application changes remain
outside this closure.
