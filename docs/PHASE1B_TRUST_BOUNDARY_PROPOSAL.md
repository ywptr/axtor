# Phase 1B trust boundary and authentication contract proposal

Axtor can proceed with internal boundary hardening and contract tests. It should
not expose authenticated domain APIs or implement a production verifier until
IS/Nexus confirms its credentials, delegation and scope contracts. Phase 1A has
correct explicit SQL scope predicates, but its context interface is not yet a
stable verified authority object, and its ORM session boundary is privileged.

This review covers clean HEAD `ff3731a` in `ywptr/axtor`. It changes documentation
only. No authentication implementation, migrations, grants, RLS changes, persistent
database access or cross-repository changes are part of this work.

## Phase 1A security review

### Findings and evidence

Locations below are repository paths. Prior Phase 1A PostgreSQL results are
historical evidence, not a claim that this review reran migrations.

| Finding | Actual evidence | Assessment and required response |
| --- | --- | --- |
| No request to context conversion | `src/axtor/main.py:create_app` has only health and readiness handlers, plus development docs. Searches of `src/` find no concrete `VerifiedServiceContext`, verifier dependency or request deserializer. `core/http.py` handles correlation only. | Pass for current production paths. There is no public tenant selector or Host-based authority. Keep a route/dependency inventory test as APIs appear. |
| Context identity can change | `core/context.py:ServiceClaims` is frozen but has an instance dictionary; a local probe changed `tenant_id` through `claims.__dict__`. `VerifiedServiceContext.verified_claims()` is an arbitrary overridable method. A second probe supplied one instance that returned tenant A, then tenant B; `_scope` accepted both against a stub reference session. | High priority before exposure. Ordinary assignment is rejected, but stable verified authority is not enforced. These are in-process boundary gaps, not remotely reachable exploits in current HTTP routes. Use a single verifier-issued snapshot with immutable nested values, no instance dictionary, no replaceable claims provider and transaction binding. Python encapsulation still cannot contain malicious process code. |
| Runtime type is not proof | `_scope` checks `isinstance(context, VerifiedServiceContext)` and `isinstance(claims, ServiceClaims)`. Any in-process subclass can return syntactically valid, unverified claims. The abstract interface has no issuer, expiry or verification receipt. | Expected unfinished boundary. Never deserialize requests into a class satisfying this interface. Restrict construction to a trusted verifier module and keep doubles in tests. Constructor hiding alone is not cryptographic verification. |
| SQL scope filters are correct within their assumptions | `persistence/repository.py:_query` requires tenant UUID and exact application/workspace with `IS NOT DISTINCT FROM`; optional policy name adds equality. `get`, `update`, `delete` resolve through this query; `create` copies scope only from claims. | Pass for a stable, authorized snapshot and an isolated clean session. NULL application/workspace means exact tenant/application scope, not wildcard. No inherited fallback. |
| Identity and scope do not grant operation permission | `_scope` validates reference existence but never evaluates calling service, actor, delegation, permitted operation or expiry. A context scoped to one profile can also create/update/delete it. `policy_profile=None` permits all names in that exact scope. | High priority before exposure. Add explicit operation permissions and permitted profile IDs; empty permissions mean deny. Local reference presence must never substitute for Nexus entitlements or application authority. |
| Session work can escape operation scope | `Database.sessions` returns raw `AsyncSession`; repository functions accept any supplied session, return attached mutable ORM models and call whole-session `flush()`. Default autoflush can run before ORM reads. No tenant/scope ownership is attached to a session. | High priority before exposure. A dirty tenant B object can be flushed during a tenant A operation; an unknown-scope rejection need not precede unrelated autoflush. A shared identity map can retain stale objects. Do not share sessions across authority contexts or tasks. Use a context-bound unit of work and immutable result objects. This is a source-based consequence, not a newly executed PostgreSQL exploit test. |
| Composite relationships are structurally sound | `models.py` and migration `0002` agree on tenant/application/workspace keys. Nullable composite FKs permit omitted scope; the workspace-requires-application CHECK closes the problematic NULL application case. Three partial unique indexes handle tenant, application and workspace names separately. | Pass by inspection; Phase 1A test source covers representative violations. FKs prove registered relationships, not membership, ownership freshness or entitlement. |
| Identity guards have a narrower purpose than lifecycle control | `0002` installs unconditional `BEFORE UPDATE OF` triggers for reference keys and profile identity/scope/name; even same-value assignments raise SQLSTATE 23514. Deletes use default NO ACTION FKs. | Guards match documentation. They do not stop deletion and recreation, owner DDL, disabling triggers or TRUNCATE. PostgreSQL test source exercises tenant/application and profile-tenant updates, but not every protected column, no-op update or delete/recreate sequence. Add those tests in the next implementation task. |
| Raw database access is privileged | Session factory and model classes are public internal APIs; there is no RLS or tenant SQL setting. Compose gives the API the same configured database user as the PostgreSQL initialization user, which is an elevated-role warning for this deployment template. Live grants were not inspected. | Do not label direct SQL as tenant-authorized. Separate runtime, reference administration and migration credentials before production. Do not infer live role attributes from the template alone. |
| Reference management has no authorized control path yet | No runtime registration functions/routes exist. Tests insert references directly with ORM. No code checks an operator identity for raw INSERT/DELETE. | Absent API is not enforcement against database principals. All future tenant registration, application association and workspace registration/removal need an explicit, audited control plane. Never create a Nexus canonical tenant in Axtor. |
| Naming and versioning are incomplete | Profile names have length/nonblank constraints, exact equality and per-scope uniqueness. Profile names and scope cannot be updated. Deletion remains available; no profile revision, tombstone or content hash exists. | Document exact current semantics and introduce immutable policy revisions before governance decisions reference policy content. Name reuse must not retarget old actions. |

SQLAlchemy documents both autoflush and the identity map; these mechanisms explain
why a correctly filtered query is insufficient to police unrelated session work.
See [SQLAlchemy session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).

### Policy names and future revisions

Today names are exact database strings; no trimming, case folding, Unicode
normalization or slug validation occurs. The CHECK rejects strings empty after
PostgreSQL `btrim` with its default space handling, not all possible whitespace.
Do not silently normalize names during authentication. Application/workspace keys
are likewise opaque exact identifiers. Bound input sizes before database writes;
UUID syntax alone does not prove a canonical tenant exists.

Proposed policy identity is `(tenant UUID, profile UUID)` with explicit scope.
Names are display/lookup labels, never durable authorization identities. Pin future
decisions to profile UUID plus immutable revision ID and content hash, retaining
the evaluated revision for audit. Separate publication/activation from revision
creation; changes create a revision rather than overwrite evaluated rules.
Reject rename/move in the runtime path; explicitly authorized replacement creates
a new resource. Define tombstones and retention before permitting deletion of
referenced profiles. Deleting and recreating a name must not satisfy an assertion
for the old UUID/revision. Existing Phase 1A descriptions are not policy rules.

## Proposed trust boundary architecture

The trust flow is:

`untrusted request → trusted credential verifier → scope resolver → immutable authority snapshot → operation authorization → context-bound unit of work → scoped repository → result DTO`

The verifier authenticates the immediate service independently of descriptive
headers. A format-specific adapter validates an IS-supported credential or an
authenticated introspection response. A resolver validates canonical tenant,
service entitlement and workspace ownership with their authoritative sources;
it never provisions missing references. An operation gate checks exact resource
selection and permissions before opening a database unit of work. Authentication
does not constitute a governance authorization decision or permission to execute
an application action.

Use one immutable snapshot per invocation, not repeated calls to a mutable claims
provider. Bind the unit of work to its snapshot fingerprint and reject reuse with
a different tenant, caller, scope or permissions. Use a fresh session per unit of
work, no concurrent task sharing, no ambient global tenant and no ORM objects
crossing its boundary. Background jobs must reverify authority at execution time;
serialized claims and old in-memory snapshots are not reusable credentials.

Only the verifier package may issue runtime snapshots; no public `from_dict`,
boolean `verified` flag, development bypass or request model may issue them.
Test fakes must not be importable through production configuration. Structural
immutability prevents accidental substitutions; trusted module ownership and
credential verification establish authority. Expiry and revocation must be checked
at the operation boundary, including queued or long-running work, rather than
assuming an earlier verification remains valid indefinitely.

Keep authentication/authorization errors generic and logs sanitized. Invalid
credentials should yield a stable authentication failure; authenticated scope or
operation denial should reveal no other tenant's record existence. Preserve safe
not-found semantics for resource lookup. Health/readiness remain unauthenticated
infrastructure probes and convey no domain authority.

## Draft internal service context contract

This is a normalized internal contract proposal, not a JWT schema or an assertion
about IS Stage 2 field names. Wire mappings require confirmation. All collections
are immutable and bounded. Missing required authority fields fail closed.

| Field | Proposed semantics |
| --- | --- |
| `contract_version` | Explicit supported internal schema version; unknown versions rejected. |
| `tenant_id` | Single canonical Nexus UUID, verified against authoritative tenant status. No Axtor generator or cross-tenant workflow context. |
| `calling_service` | Namespaced principal `(issuer, subject, kind=service)` of the immediate authenticated caller, independently bound to transport/credential proof. Application ID is a separate concept. |
| `originating_actor` | Namespaced `(issuer, subject, kind=human/agent/service)` with validated origin evidence. Service kind supports explicitly authorized autonomous calls; absence must not silently become a service actor. |
| `delegation` | Ordered oldest-to-newest immutable validated hop records; each carries delegator, delegate, tenant, authority bounds, audience, validity, assertion/evidence reference and parent linkage where supported. Direct use has an explicit mode and empty chain. |
| `authorized_scope` | Explicit discriminated exact tenant, application or workspace scope; application/workspace composite ownership is verified. For initial implementation authorize one exact scope per invocation to avoid accidental cross-products. NULL is not wildcard authority. |
| `permitted_profiles` | Explicit finite set of profile UUIDs, with revision bounds when available. Empty means no profile authority. Creating a new profile requires a separate operation grant in the exact scope; it cannot be inferred from possession of an existing profile. No implicit all-profiles value. |
| `permitted_operations` | Explicit bounded permissions, such as profile read/create/update/delete, separate from future adjudication and execution authority. Permissions are narrowed at each delegation. Names are provisional until the API contract is agreed. |
| `credential_evidence` | Trusted issuer, recipient audience, assertion type/version, credential identifier/fingerprint, authenticated service binding, validation method and signing key ID if relevant. Never store raw bearer tokens in the context or logs. |
| `validity` | Issued-at, not-before, expiry, verification time, approved clock skew and maximum age. Effective expiry cannot exceed any relied-upon authority. |
| `revocation_evidence` | Authoritative status source, checked-at time, status/version and freshness deadline. An accepted credential remains subject to permission and tenant-lifecycle revocation. |
| `replay_binding` | Assertion ID/nonce, recipient, authenticated sender and operation/request binding for assertions defined as single-use. Durable consumption state is separate from the context. |
| `verified_parent_action` | Optional validated tenant-bound parent reference with authenticated provenance if used for authorization or action linkage. Missing or inaccessible parents cannot confer authority. |

Descriptive `RequestMetadata` is a separate value: correlation ID, trace IDs,
requested resource selector, caller-supplied parent reference, user agent and
optional labels. Current `X-Correlation-ID` is sanitized caller input, never proof
of caller, tenant, delegation or action lineage. A requested parent reference only
becomes verified lineage after tenant-scoped lookup and permission checks. A
correlation ID never provides replay protection. A requested profile/workspace
selects within the authority snapshot and cannot expand it.

## Authentication mechanism assessment

| Mechanism | Fit and constraints |
| --- | --- |
| OAuth service credentials | Prefer independently issued service credentials over shared API keys. Confirm whether IS supports client credentials and asymmetric client authentication. Service authentication alone provides no human delegation or tenant grant. |
| JWT access assertions | Suitable if IS supports them. Pin issuer, algorithms, token type and intended Axtor audience; validate signature, required claims, validity and key provenance. Never accept an ID token as an API access token or follow token-supplied key URLs. JWT expiry does not give immediate revocation. See [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.txt). |
| Opaque token plus introspection | Suitable alternative if IS exposes authenticated introspection with required actor/scope evidence. Active status is not enough without audience, principal and scope validation. Define cache freshness and outage behavior; deny when required evidence is unavailable. See [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.txt). |
| Mutual TLS and certificate-bound tokens | Prefer when workload PKI and ingress can preserve authenticated client binding. Validate the presented certificate against token binding; a TLS certificate alone does not prove originator or tenant permission. Do not trust arbitrary forwarded certificate headers. See [RFC 8705](https://www.rfc-editor.org/rfc/rfc8705.txt). |
| DPoP sender binding | Consider when end-to-end mTLS is impractical and IS supports DPoP. It binds token use to a key and request proof; requires nonce/proof replay validation and careful URI handling. It does not provide application idempotency or bind arbitrary request bodies by itself. See [RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.txt). |
| Token exchange | Preferred multi-hop mechanism if IS supports it: each caller obtains a narrowed assertion for the next recipient, preserving origin and attesting delegation. No transparent bearer forwarding across audiences. See [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.txt). |
| Shared API keys or identity headers | Insufficient for the complete contract. Avoid as a provisional production substitute; they do not establish validated originator, delegation and exact tenant authority. |

No mechanism above is confirmed available in IS Stage 2. Choose JWT verification
or opaque introspection through an adapter after its contract is supplied, not by
inventing a suite-wide format inside Axtor. Provisioning remains IS/Nexus owned.

## Delegation validation design

1. Authenticate the immediate service and validate the credential's issuer,
   recipient, type, validity and revocation evidence. If proof of possession is
   required, bind the credential to this service's proof. Reject conflicts among
   transport identity and signed/introspected identity.
2. Resolve the originator from authoritative evidence. Preserve issuer/subject
   identity across hops; a caller-supplied actor string is descriptive only.
3. Decode a bounded ordered chain using an explicit format mapping. Reject
   malformed links, cycles, repeated service loops, missing links, excessive
   depth, unsupported delegation modes and an endpoint inconsistent with the
   authenticated immediate caller.
4. Validate issuer-attested chain integrity or each independently authenticated
   delegation link, depending on the agreed protocol. Caller-supplied lists cannot
   serve as evidence. All relied-upon links must bind the same canonical tenant;
   explicit conflicting tenant information causes rejection, not precedence rules.
5. Compute effective scope/permissions as the intersection of originator authority,
   immediate service grants, issuer-attested delegation bounds, Nexus entitlements
   and consumer-owned workspace authority. Never union privileges from different
   hops. A hop can narrow authority but cannot change tenant, reset originator or
   extend validity. Fail on stale/unknown authority.
6. Resolve the requested exact application/workspace/profile within those bounds.
   Check all identifiers as composite resource references. A service-to-application
   mapping is explicit; an IG principal is not automatically restricted to, or
   authorized for, the application named IG.
7. Validate verified parent lineage and consume a single-use assertion atomically
   when its defined semantics require it. Issue the immutable internal snapshot
   only after every required check succeeds.

For Sandcastle → IG → Axtor, an originator U in tenant T first delegates a bounded
operation through Sandcastle. IG receives a credential intended for IG, then
obtains a new assertion intended for Axtor with IG as immediate caller, U as
originator and a validated history containing Sandcastle then IG. Axtor rejects
an IG-audience credential, an asserted caller of Sandcastle on an IG-bound request,
a changed tenant or a profile/workspace outside the effective bounds. If IS cannot
attest the history or validate equivalent link evidence, delegated runtime access
remains unavailable; do not synthesize provenance from request headers.

RFC 8693 represents current actor with the outer `act` and older actors inside;
its historical actors are informational, not independent access-control grants.
Normalize that order carefully. Enforce effective top-level authority/current
actor; any stricter linked-evidence contract must be explicitly agreed rather than
derived from historical `act` names. See [RFC 8693 section 4.1](https://www.rfc-editor.org/rfc/rfc8693.txt).

Use distinct replay rules for reusable access credentials and single-use action
assertions. A short lifetime or `jti` alone does not prevent replay. For single-use
assertions, atomically reserve a trusted `(issuer, audience, assertion ID)` and bind
it to tenant, caller and a canonical operation/request digest; retain it through
expiry plus skew. Concurrent duplicate consumption must produce at most one
accepted operation. Specify how reservation, transaction rollback and safe retry
interact. Idempotency keys are separate, tenant/caller/operation scoped and cannot
refresh expired authority. Reusing a bearer access token is not automatically a
replay violation unless the agreed credential semantics make it single-use.

Credential rotation needs pinned trust configuration, bounded key-cache refresh,
overlap for planned signing-key rotation and explicit compromised-key removal.
Unknown keys must trigger only bounded refresh from configured issuer endpoints.
Define maximum revocation delay and cache age with IS/Nexus; never accept stale
status indefinitely during an outage. A revoked service, actor, tenant, entitlement
or delegated grant must invalidate its dependent authority within that agreed bound.

## PostgreSQL isolation recommendation

Introduce tenant RLS as defense in depth in a separate reviewed implementation
before exposing tenant data to authenticated consumers. Retain repository filters
and operation authorization. Initial RLS should cover every tenant-owned table:
`tenant_references`, `tenant_applications`, `workspace_references`, `policy_profiles`.
The global application registry can be runtime read-only. Application/workspace
and profile permissions remain checked by the operation layer; tenant RLS alone
does not enforce those narrower permissions.

PostgreSQL RLS supports separate visibility and write checks; owners normally
bypass it, and superusers/`BYPASSRLS` roles always bypass it. Plan both `USING` and
`WITH CHECK`, with `FORCE ROW LEVEL SECURITY` where appropriate. Referential
integrity checks can bypass RLS, so constraint errors need safe translation.
See [PostgreSQL 17 row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

### Context and pooling

The trusted unit of work must open an explicit transaction, install a canonical
UUID from its verified snapshot using a parameterized transaction-local setting
such as `SELECT set_config('axtor.tenant_id', :tenant, true)`, then perform all
queries and flushes on that same transaction/connection. This is illustrative
future design, not an operator command for this task. Missing/empty settings must
deny access; malformed UUID settings must error or deny, never choose a fallback.
Do not accept a setting value from arbitrary request metadata.

Transaction-local settings end at commit/rollback. Never install authority with
session-level `SET` or on a pool checkout independently of the business transaction.
Savepoint rollback can revert settings, so initialize at outer transaction entry
and prohibit changes from nested units. Reinitialize on each fresh transaction;
a reconnect or retry requires verified context rebinding. See
[PostgreSQL 17 SET](https://www.postgresql.org/docs/17/sql-set.html).

Pool connection reuse is allowed; ORM session/identity-map reuse between authority
contexts is not. Reject sessions already bound to another snapshot or containing
unexpected pending/dirty objects. On cancellation/error, roll back and close the
unit; invalidate connections with uncertain cleanup. Rollback-on-return is useful
cleanup, not the authorization mechanism. Test pool size one with sequential and
concurrent tenants, failures, cancellation, nested transactions and connection loss.

A custom tenant setting is writable by code holding that database connection.
RLS backed by such a setting protects against omitted predicates; it does not
contain arbitrary SQL execution or a compromised runtime that changes the setting.
If that threat must be contained, evaluate a trusted database gateway or narrowly
executable routines with independently verified authority. Do not claim the
custom-setting design solves credential compromise.

### Proposed roles and elevated operations

| Role | Proposed privileges and use |
| --- | --- |
| Runtime | Non-owner, non-superuser, no BYPASSRLS, no membership permitting SET ROLE to an owner; only required reads and profile DML, no reference registration, DDL, TRUNCATE or trigger administration. |
| Reference control plane | Separate credential/process for authorized canonical reference registration, application/workspace associations, removals and reconciliation. Bounded by Nexus/application evidence and audited actor/reason. No general runtime fallback. |
| Migration owner | Explicit operator-only schema ownership, migrations, RLS policies, functions and grants; never injected into API containers. |
| Emergency administration | Separate audited operational access for repair, backup/restore and required cross-tenant maintenance; unavailable to runtime code. |

Do not share a privileged connection pool with runtime or perform privilege
switches inside a request. A runtime role posture check should reject elevated
roles at deployment/startup without mutating grants. Keep administration imports
and credential configuration separate; missing runtime credentials must not fall
back to operator credentials. Review function ownership/search path, public schema
creation rights and future SECURITY DEFINER routines. Schema validation must
include actual roles/policies, not merely Alembic metadata drift checks, which do
not establish trigger/RLS behavior.

## Adversarial test matrix

Status: **Now** means implementable against current code or deterministic internal
contract doubles, without assuming an IS wire format. These are specifications,
not newly added passing tests. **Contract** means real credential fixtures and
acceptance criteria depend on confirmed IS Stage 2 behavior. PostgreSQL cases
require separately authorized disposable database tests; none run in this review.
Every denial should verify no unintended writes, no cross-tenant data in responses
or logs and no privileged fallback.

| Attack | Negative case and expected outcome | Availability |
| --- | --- | --- |
| Forged caller identity | Alter service headers/body while presenting no verified context; reject. With a real token, mismatched sender/principal proof must reject. | Now: request path/type checks; Contract: proof binding. |
| Forged canonical UUID | Change request tenant or inject raw `ServiceClaims`; no context issuance or scope override. Correctly signed but unauthorized tenant must also reject. | Now: selection/type checks; Contract: tenant authority. |
| Snapshot substitution | Mutate claims via `__dict__`; alternate snapshots from one provider; attempt mutation between validation and flush. Future boundary must reject or be structurally incapable. | Now; current probes expose gaps. |
| Cross-tenant delegation | A link or parent says tenant B while effective authority says A; reject entire request, even if actor belongs to both. | Now: invariant doubles; Contract: attested evidence. |
| Incorrect audience | Token for IG, Nexus or another deployment presented to Axtor, or missing/ambiguous audience; reject with no alternate validator fallback. | Contract; gate semantics can be specified now. |
| Expired credentials | At/after expiry, before not-before, excessive lifetime/future issue time or clock skew beyond agreed bound; deny, including queued execution. | Now: fake-clock invariants; Contract: time semantics. |
| Revoked credentials | Revoked service/key/actor/delegation or stale introspection cache; deny within agreed SLA. Outage cannot bypass checks. | Contract: source, TTL and outage SLA. |
| Malformed delegation | Reverse order, broken adjacency, cycle, duplicate loop, truncation, excessive depth or unknown principal kind; reject. | Now: normalized chain doubles; Contract: wire mapping. |
| Privilege escalation | Child adds profile write, expands workspace, changes tenant or extends expiry; deny instead of merging grants. | Now: intersection rules; Contract: issued bounds. |
| Caller/originator substitution | IG swaps originator U for V or claims Sandcastle is immediate caller; reject inconsistency without overwriting trusted evidence. | Now: normalized invariants; Contract: principal proof. |
| Unauthorized workspace | Same workspace string under another tenant/application, unknown workspace or missing current entitlement; deny. | Now: existing FK/repository coverage; Contract: authority freshness. |
| Policy substitution | Requested profile outside finite allowed UUIDs, reused name with new UUID, wrong revision/hash, profile with same name in another scope; deny. | Now: current exact-scope tests and future normalized gate tests; Contract: permitted-profile encoding. |
| Replayed assertion | Concurrent same single-use assertion, changed body with same ID, retry after partial failure or after expiry; at most one accepted matching operation. Correlation ID reuse grants nothing. | Now: atomic-consumption model tests; Contract: assertion semantics/binding. |
| Multi-hop tenant conflict | Sandcastle evidence T1, IG evidence T2, Axtor request T1 or parent in T2; reject all conflicting combinations. | Now: normalized fixtures; Contract: end-to-end exchange. |
| Unauthorized operation | Read-only authority calls profile create/update/delete; empty permissions and absent profile restrictions must not become broad grants. | Now: design tests; current repository has no operation gate. |
| Session contamination | Dirty B object then A read/write/unknown scope; no B flush. Reuse identity map or returned ORM object across contexts; reject ownership violation. | Now: disposable PostgreSQL regression specification; current gap. |
| Database bypass | Runtime SQL without tenant setting, wrong tenant inserts, UPDATE to another tenant; deny under proposed RLS. Operator role cannot enter runtime pool. | Now: future disposable role/RLS test plan. |
| Identity and lifecycle escape | Update each guarded column, same-value UPDATE, FK reassignment, delete/recreate names, TRUNCATE by runtime; constrain as specified. | Now: disposable PostgreSQL test plan. |
| Key and token confusion | Wrong issuer/type, unsigned token, algorithm confusion, unknown key or untrusted key URL; reject without outbound arbitrary URL fetch. | Contract: supported token profile and key distribution. |
| Unauthorized registration | Runtime or missing authority attempts reference insert/remove or auto-provision on unknown UUID; deny and retain no side effects. | Now: no-route checks and future role tests; Contract: provisioning evidence. |

## Exact IS and Nexus contract questions

These are handoff questions for the owning teams; no cross-application changes or
messages were performed. Answers must become versioned contracts and test fixtures.

1. **IS:** Which Stage 2 mechanisms actually exist for workload authentication:
   OAuth client credentials, signed access assertions, opaque introspection, mTLS,
   asymmetric client authentication or another protocol? Provide supported versions,
   discovery/trust configuration and nonproduction fixtures.
2. **IS:** What are exact issuer identifiers, Axtor audience/resource identifiers
   per environment, accepted credential types and algorithm/key constraints? Are
   multi-audience credentials allowed, and how is cross-environment use rejected?
3. **IS:** Which authoritative fields distinguish immediate service principal from
   originator? Are identities issuer/subject pairs, what actor kinds exist, and
   how are autonomous agents bound to their accountable principal?
4. **IS:** Is audience-restricted token exchange or an equivalent attested
   delegation protocol supported? What are the chain ordering, direct-call mode,
   maximum depth, current-actor mapping and integrity/truncation guarantees?
5. **IS/Nexus:** Which authority validates each hop and enforces narrowing? Can
   authority be delegated from Sandcastle to IG for an Axtor operation without
   changing tenant/originator? Supply valid and invalid end-to-end examples.
6. **Nexus:** What is the exact canonical tenant UUID field and lifecycle status
   contract? How are disabled/deleted/unknown tenants handled, and are UUIDs ever
   reused? How is lifecycle freshness communicated to Axtor without Axtor owning it?
7. **Nexus:** How does Axtor verify service/application entitlements and required
   actor membership/delegated eligibility? Are those issuer-attested claims or
   online queries? Specify authority, version, cache TTL and outage behavior.
8. **Nexus and consumer owners:** Who attests application/workspace composite
   ownership and access? What are exact key formats, case semantics, workspace
   lifecycle/reuse rules and authoritative lookup contracts? No global workspace
   string may be sufficient evidence.
9. **IS/Axtor:** How are permitted operations and finite profile UUID/revision
   bounds represented? Who resolves Axtor-owned profile permissions, and how is
   profile creation authority expressed separately from access to existing IDs?
10. **IS:** What are maximum credential lifetime, skew, accepted issue age,
    revocation sources, maximum revocation delay, refresh behavior and availability
    guarantees? How do actor, tenant, entitlement and delegation revocations flow?
11. **IS:** How are signing keys/workload certificates rotated and compromised
    keys revoked? What are overlap, cache refresh, emergency removal and sender
    binding requirements, including TLS termination at proxies?
12. **IS/Axtor:** Which credentials are reusable versus single-use? What binds an
    assertion to tenant/caller/audience/operation/payload, what is its nonce/ID
    uniqueness domain, and what retry/rollback/idempotency semantics are required?
13. **IS/Nexus/Axtor:** What proves parent-action lineage across applications?
    Which identifiers are observability-only, and which must be signed or resolved
    through versioned APIs? How is a tenant mismatch rejected across the workflow?
14. **Nexus/Axtor:** What explicitly authorized process registers and reconciles
    local tenant/application references? Which evidence, operator identity, audit,
    removal and revocation rules apply? Confirm it never creates canonical tenants
    or maintains an independent shared membership/entitlement database.
15. **All owners:** Which `/v1` contracts, compatibility rules, safe failure codes,
    test environments and joint negative fixtures will be accepted before rollout?

## Implementation sequence and decision

1. Agree on the normalized invariants and record answers to the questions above.
   Freeze exact null/empty scope semantics, profile identity and operation grants.
2. In a separately authorized Axtor task, replace mutable claims-provider usage
   with verifier-owned snapshots and context-bound units of work. Return immutable
   DTOs, isolate sessions and add mutation, substitution and dirty-session tests.
   Keep production issuers/routes absent during this step.
3. Define the authorized reference-control path, role separation and rollout
   checks. Design RLS in an explicit revision and test it under actual runtime
   roles on disposable PostgreSQL, including pooling and fail-closed behavior.
   Persistent changes remain separate operator actions requiring approval.
4. Once IS confirms its contract, implement one format-specific authentication
   adapter with pinned trust, actor/delegation validation, scope resolution, expiry,
   revocation and sender/replay protections appropriate to that contract.
5. Verify operation gates, finite profile selection and parent linkage before
   connecting any `/v1` domain route. Keep proposal, adjudication, authorization
   and execution separate in the API and permission model.
6. Run the complete adversarial matrix with IS/Nexus and consumer fixtures; check
   privilege posture, race/retry behavior and sanitized observability. Review and
   approve rollout independently of implementation completion.

**Go:** internal boundary hardening, deterministic contract tests, database security
design and IS/Nexus contract negotiation.

**No-go:** production authentication, tenant-facing domain endpoints or claims that
Phase 1A already enforces authenticated authorization. Blocking issues are unstable
context snapshots, missing operation authority, unrestricted session ownership and
unconfirmed credential/delegation/authority contracts. Production rollout also
requires tested runtime role separation and the approved database isolation plan.

## Verification for this review

Read the implementation, migration, configuration and tests rather than relying on
the prior report. Local no-database probes confirmed ordinary frozen assignment
rejection, dictionary mutation and changing claims from the same context instance.
No production path currently invokes such a context. No migration tests were run;
the PostgreSQL integration test was explicitly disabled for this review because
it performs DDL and downgrades. The prior Phase 1A report remains the historical
source for its 34-test PostgreSQL run.

Current review checks: **33 passed, 1 skipped** with
`AXTOR_TEST_DISPOSABLE_DATABASE_URL` removed from the test environment. All 20
Phase 0 regression tests passed. Ruff, formatting, strict Mypy and
`git diff --check` passed. The existing Starlette/httpx deprecation warning remains.
The only repository change is this proposal; application functionality and database
objects are unchanged.
