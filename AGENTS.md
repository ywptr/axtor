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
