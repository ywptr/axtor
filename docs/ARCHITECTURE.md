# Repository instructions

This repository is `ywptr/axtor`, the independent API-first AI Action Governance
Engine. Never modify `sociosight/axtor`, a separate website project.

## Ownership and boundaries

- Axtor owns AI action governance and authorization.
- IS owns authentication.
- IS/Nexus owns the canonical tenant UUID.
- Nexus owns tenant lifecycle, shared membership and application entitlements.
- Sandcastle and IG own their application resources and enforcement.
- Axtor does not independently create canonical tenants.
- Keep proposal, adjudication, authorization and execution distinct.
- Calling service, initiating actor, tenant and delegation chain are separate identity concepts.
- Isolate every tenant-owned resource using the canonical tenant UUID.
- Runtime consumers communicate through versioned APIs (future domain APIs use `/v1`).
- Report cross-application changes as handoffs; never perform them here.

## Development

Phase 0 includes configuration, API bootstrap, persistence infrastructure and tests
only. No authentication bypasses, tenant operations, governance logic, external AI
providers or production database connections. Migrations are explicit operator
commands, never application startup side effects. Preserve existing work and never
commit or push without authorization. Keep secrets out of source and error bodies.

Run `ruff check .`, `ruff format --check .`, `mypy`, and `pytest` in the installed
virtual environment. Validate migrations against disposable PostgreSQL before
shipping schema changes. Do not replace PostgreSQL coverage with SQLite.

## Phase 0 design

`create_app` validates environment configuration before serving traffic. Engine
creation is lazy: startup does not connect, migrate, or create tables. Each worker
owns a bounded async SQLAlchemy pool (5 connections plus 5 overflow by default),
with pre-ping and bounded acquisition, connection and readiness deadlines. Shutdown
disposes the pool. Session transactions will be owned by future use cases; the
session factory does not implicitly commit.

`/health` is process liveness; `/ready` executes `SELECT 1` and returns 503 on
failure. Readiness confirms connectivity only, not migration currency. Operators
must run migrations before rollout. The empty baseline creates only Alembic's
version table. No domain tables exist.

Errors share an envelope containing code, safe message and correlation ID. Caller
IDs accept 1–128 ASCII letters, digits, dots, underscores and hyphens; other values
are replaced with a UUID. Correlation IDs are untrusted observability metadata,
never identity or authorization. Unexpected errors log a correlation ID without
exception text that might contain credentials. Production tracing and sanitized
structured diagnostics remain future work.

No CORS middleware is enabled. Docs and OpenAPI are enabled in development/test
and disabled in production. Containers run as an unprivileged user, with published
local ports bound to loopback. Production requires TLS termination, secret
injection, deployment-specific database security and an operational rollout plan.
Future domain APIs must document versioned contracts before consumer adoption.
