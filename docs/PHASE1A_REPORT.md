# Phase 1A: Canonical tenant foundation

## Scope and preparation

Started from clean HEAD `bf03aab`. Inspected architecture, configuration, async
session ownership, Compose networking, Alembic environment, empty `0001` baseline,
and existing tests. The original 20 tests passed before implementation. `0001`
is unchanged; `0002` is its sole successor. No HTTP domain routes were added.

Design chosen before implementation: externally supplied canonical tenant UUIDs,
stable application keys, composite tenant/application/workspace references, exact
policy scope, and a verifier interface with no production implementation.
The Phase 0-only restriction describes the previous phase; this requested Phase 1A
extends persistence only, preserving startup, configuration and HTTP safeguards.

## Schema and constraints

- `tenant_references`: Nexus UUID primary key, no client or server default.
- `consumer_applications`: nonblank application string primary key; Sandcastle and
  IG are supported reference values, not automatically seeded.
- `tenant_applications`: composite tenant/application primary key and restrictive
  foreign keys. A local reference association is not an entitlement grant.
- `workspace_references`: composite tenant/application/workspace primary key;
  composite foreign key to the tenant/application association, nonblank workspace.
- `policy_profiles`: composite tenant/profile UUID primary key; explicit tenant FK,
  tenant/application FK, and tenant/application/workspace FK. Workspace requires
  application. Profile UUIDs are local resource IDs, not canonical tenant IDs.
  Nonblank profile names; three partial unique indexes enforce name uniqueness
  separately for tenant, application and workspace scopes, including NULL scopes.
  Profiles contain only name and description, with no governance rules or decisions.

Foreign keys use PostgreSQL's restrictive defaults without cascading deletions.
Triggers reject updates to canonical UUIDs, application identities, association
and workspace keys, and profile identity/scope/name. Even a no-op assignment to an
identity column is rejected. Only profile descriptions have a repository update
operation. There is no automatic registration, membership or entitlement store.
Reference registration must be an explicit controlled operator action using
externally established identities; no runtime provisioning interface is supplied.

## Context and isolation

`ServiceClaims` is an immutable, validated claim value containing canonical UUID,
calling service, originating actor, ordered delegation provenance, and optional
application, workspace and policy name scope. Empty delegation means direct use;
nonempty elements are opaque provenance pending a formal Phase 1B contract.
Claims alone are untrusted and rejected by repository functions.

`VerifiedServiceContext` is an abstract internal verifier contract. Phase 1A has no
concrete runtime implementation, factory, HTTP dependency, credential validator or
conversion of request data into this interface. Tests use an explicitly test-only
implementation. A future trusted adapter must verify both identities and authority
to the complete scope before returning claims.

Every public profile repository function requires a verified context, checks
registered tenant/application/workspace references, and constrains SQL to exact
tenant, application and workspace scope, plus policy name if restricted. There is
no tenant argument override, global fallback, parent-scope inheritance or Host
inference. Cross-scope IDs produce the same not-found result as absent IDs.
Unknown references fail closed. Transactions and commits remain caller owned.

This provides repository isolation and relational consistency, not PostgreSQL row
level security. Direct SQL, raw ORM/session use, database owners and malicious
in-process implementations of the abstract interface remain privileged. Composite
foreign keys prevent mismatched scope references but cannot authorize arbitrary
SQL reads. Phase 1B must define trusted verifier ownership, transaction/session
usage, grants, authorization rules and any additional database defense. No
proposal, adjudication, authorization decision or execution was implemented.

## Migration and verification

`0002` creates only new tables, indexes, identity triggers and their function.
Upgrade does not rewrite existing data. Downgrade removes Phase 1A records and
objects, so operators must explicitly approve any persistent downgrade. Startup
still never runs migrations. Persistent development and production databases
were not migrated, downgraded or stamped.

Verification used installed PostgreSQL 17 binaries with a fresh disposable cluster
under `/tmp/axtor-phase1a-pg`, bound to loopback port 55483. Docker access was
unavailable; daemon permissions and existing network configuration were unchanged.
The cluster was stopped after verification.

Results: 34 tests passed, including all 20 Phase 0 tests. PostgreSQL tests cover
shared applications across tenants, multiple applications per tenant, multiple
profiles, repeated workspace names, exact scope isolation, cross-tenant and
cross-scope reads/updates/deletes, unknown references, duplicate references,
missing canonical UUIDs, profile uniqueness in all scope variants, invalid
workspace/application combinations, foreign keys and immutable identity triggers.
Context tests reject malformed claims, missing/unverified contexts and direct
instantiation of the verifier interface.

Disposable migration sequence: base → 0001 → 0002 → 0001 → 0002 → base.
Alembic `check` passed after each upgrade to 0002. Unrelated existing sentinel data
survived upgrades and downgrades. Ruff, Ruff formatting and strict Mypy passed.
The suite reports an existing Starlette/httpx deprecation and the expected
SQLAlchemy warning when testing omission of the canonical tenant primary key.

To rerun integration tests, point `AXTOR_TEST_DISPOSABLE_DATABASE_URL` at a fresh,
empty, disposable PostgreSQL database and run `.venv/bin/pytest`. This test performs
DDL and destructive downgrades. Without that explicit variable it skips PostgreSQL
integration coverage; never point it at persistent development or production.

## Handoff and next task

No other repository changes were made. No IS/Nexus contract change is necessary
to land this persistence work. Before Phase 1B, agree with IS/Nexus on issuer and
audience trust, canonical UUID claim naming, service versus originating actor
identities, delegation semantics, expiry/replay/revocation handling, scope authority,
and how verified canonical references reach Axtor. Nexus continues to own lifecycle,
shared membership and entitlements; local reference presence never proves access.
Consumer applications remain authoritative for workspace/resource ownership.

Recommended next task: Phase 1B verified service-context contract and adapter,
with adversarial authentication and scope-validation tests before any `/v1`
governance API is exposed. Do not add a temporary authentication bypass.

## Files changed

- `src/axtor/core/context.py`: immutable claim values and verifier boundary.
- `src/axtor/persistence/models.py`: relational reference and profile models.
- `src/axtor/persistence/repository.py`: scoped profile operations.
- `alembic/versions/0002_tenant_foundation.py`: explicit schema and identity guards.
- `alembic/env.py`: load metadata for operator schema checks.
- `tests/test_tenant_foundation.py`: context and real PostgreSQL coverage.
- `docs/ARCHITECTURE.md`: current phase reference.
- `docs/PHASE1A_REPORT.md`: design, verification, limitations and handoff.
