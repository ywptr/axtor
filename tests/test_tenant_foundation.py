"""PostgreSQL tests require an explicitly designated disposable database URL."""

import asyncio
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from axtor.core.context import ServiceClaims, VerifiedServiceContext
from axtor.persistence.database import Base
from axtor.persistence.models import (
    ConsumerApplication,
    PolicyProfile,
    TenantApplication,
    TenantReference,
    WorkspaceReference,
)
from axtor.persistence.repository import (
    InvalidContext,
    ProfileNotFound,
    UnknownScope,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)


@dataclass(frozen=True)
class TestVerifiedContext(VerifiedServiceContext):
    __test__ = False
    claims: ServiceClaims

    def verified_claims(self) -> ServiceClaims:
        return self.claims


def verified(
    tenant: UUID,
    app: str | None = None,
    workspace: str | None = None,
    profile: str | None = None,
) -> TestVerifiedContext:
    return TestVerifiedContext(
        ServiceClaims(tenant, "test-service", "test-actor", (), app, workspace, profile)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "unverified"},
        {"calling_service": ""},
        {"originating_actor": ""},
        {"delegation": ["mutable"]},
        {"delegation": ("",)},
        {"workspace_id": "orphan"},
        {"application_id": " "},
    ],
)
def test_invalid_claims(changes: dict[str, Any]) -> None:
    fields: dict[str, Any] = dict(
        tenant_id=uuid4(), calling_service="svc", originating_actor="actor", delegation=()
    )
    fields.update(changes)
    with pytest.raises(ValueError):
        ServiceClaims(**fields)


def test_no_runtime_issuer() -> None:
    with pytest.raises(TypeError):
        VerifiedServiceContext()  # type: ignore[abstract]


@pytest.mark.parametrize(
    "context", [None, {}, uuid4(), "tenant", ServiceClaims(uuid4(), "svc", "actor", ())]
)
def test_unverified_context_rejected(context: Any) -> None:
    async def scenario() -> None:
        # Rejected before touching even a session object.
        with pytest.raises(InvalidContext):
            await list_profiles(None, context)  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_postgres_migrations_and_isolation() -> None:
    url = os.environ.get("AXTOR_TEST_DISPOSABLE_DATABASE_URL")
    if not url:
        pytest.skip("Set AXTOR_TEST_DISPOSABLE_DATABASE_URL; this test migrates and drops tables")
    environment = {**os.environ, "AXTOR_DATABASE_URL": url}

    def migrate(*args: str) -> None:
        subprocess.run(
            [".venv/bin/alembic", *args],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    async def scenario() -> None:
        engine = create_async_engine(url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        a, b, unknown = uuid4(), uuid4(), uuid4()

        async def violates(operation: Callable[[AsyncSession], None]) -> None:
            async with sessions() as session, session.begin():
                with pytest.raises(IntegrityError):
                    async with session.begin_nested():
                        operation(session)
                        await session.flush()

        try:
            async with engine.begin() as conn:
                # Preexisting unrelated data must survive upgrades and downgrades.
                await conn.execute(text("CREATE SCHEMA existing_data"))
                await conn.execute(
                    text("CREATE TABLE existing_data.phase0_sentinel (value integer)")
                )
                await conn.execute(text("INSERT INTO existing_data.phase0_sentinel VALUES (42)"))
            await asyncio.to_thread(migrate, "upgrade", "0001")
            await asyncio.to_thread(migrate, "upgrade", "head")
            await asyncio.to_thread(migrate, "check")
            async with sessions() as s, s.begin():
                s.add_all(
                    [
                        TenantReference(tenant_id=a),
                        TenantReference(tenant_id=b),
                        ConsumerApplication(application_id="sandcastle"),
                        ConsumerApplication(application_id="ig"),
                    ]
                )
                await s.flush()
                s.add_all(
                    [
                        TenantApplication(tenant_id=t, application_id=app)
                        for t, app in [(a, "sandcastle"), (b, "sandcastle"), (a, "ig")]
                    ]
                )
                await s.flush()
                s.add_all(
                    [
                        WorkspaceReference(tenant_id=t, application_id=app, workspace_id=w)
                        for t, app, w in [
                            (a, "sandcastle", "shared"),
                            (b, "sandcastle", "shared"),
                            (a, "ig", "ig-only"),
                        ]
                    ]
                )
                await s.flush()
                p = await create_profile(s, verified(a), "default")
                await create_profile(s, verified(a), "strict")
                await create_profile(s, verified(b), "default")
                app_profile = await create_profile(s, verified(a, "sandcastle"), "default")
                await create_profile(s, verified(a, "ig"), "default")
                w = await create_profile(s, verified(a, "sandcastle", "shared"), "default")
                await create_profile(s, verified(b, "sandcastle", "shared"), "default")
                assert len(await list_profiles(s, verified(a))) == 2
                assert len(await list_profiles(s, verified(a, "sandcastle"))) == 1
                assert len(await list_profiles(s, verified(a, profile="strict"))) == 1
                for bad in [
                    verified(b),
                    verified(a, "ig"),
                    verified(a, "sandcastle", "shared"),
                    verified(a, profile="strict"),
                ]:
                    with pytest.raises(ProfileNotFound):
                        await get_profile(s, bad, p.profile_id)
                    with pytest.raises(ProfileNotFound):
                        await update_profile(s, bad, p.profile_id, "cross-scope")
                    with pytest.raises(ProfileNotFound):
                        await delete_profile(s, bad, p.profile_id)
                for bad in [
                    verified(unknown),
                    verified(b, "ig"),
                    verified(a, "ig", "shared"),
                    verified(a, "sandcastle", "ig-only"),
                ]:
                    with pytest.raises(UnknownScope):
                        await list_profiles(s, bad)
                    with pytest.raises(UnknownScope):
                        await create_profile(s, bad, "fail")
                with pytest.raises(InvalidContext):
                    await create_profile(s, verified(a, profile="strict"), "other")
                await update_profile(s, verified(a), p.profile_id, "updated")
                await delete_profile(s, verified(a, "sandcastle"), app_profile.profile_id)
                assert (await get_profile(s, verified(a), p.profile_id)).description == "updated"
                assert (
                    await get_profile(s, verified(a, "sandcastle", "shared"), w.profile_id)
                ) == w
            for record in [
                TenantReference(tenant_id=a),
                TenantReference(),
                ConsumerApplication(application_id="sandcastle"),
                TenantApplication(tenant_id=b, application_id="missing"),
                WorkspaceReference(tenant_id=b, application_id="ig", workspace_id="x"),
                PolicyProfile(tenant_id=unknown, name="x"),
                PolicyProfile(tenant_id=a, name="default"),
                PolicyProfile(tenant_id=a, application_id="ig", name="default"),
                PolicyProfile(
                    tenant_id=a, application_id="sandcastle", workspace_id="shared", name="default"
                ),
                PolicyProfile(tenant_id=a, workspace_id="shared", name="invalid"),
                PolicyProfile(tenant_id=b, application_id="ig", name="invalid"),
                PolicyProfile(
                    tenant_id=a, application_id="ig", workspace_id="shared", name="invalid"
                ),
            ]:

                def add(session: AsyncSession, record: Base = record) -> None:
                    session.add(record)

                await violates(add)
            async with sessions() as s, s.begin():
                for sql in [
                    "UPDATE tenant_references SET tenant_id = :new WHERE tenant_id = :old",
                    "UPDATE consumer_applications SET application_id = 'changed'",
                    "UPDATE policy_profiles SET tenant_id = :new",
                    "DELETE FROM tenant_references WHERE tenant_id = :old",
                ]:
                    with pytest.raises(IntegrityError):
                        async with s.begin_nested():
                            await s.execute(text(sql), {"old": a, "new": unknown})
            await asyncio.to_thread(migrate, "downgrade", "0001")
            async with engine.connect() as conn:
                assert (
                    await conn.scalar(text("SELECT value FROM existing_data.phase0_sentinel")) == 42
                )
                assert await conn.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
            await asyncio.to_thread(migrate, "upgrade", "head")
            await asyncio.to_thread(migrate, "check")
            await asyncio.to_thread(migrate, "downgrade", "base")
            async with engine.connect() as conn:
                assert (
                    await conn.scalar(text("SELECT value FROM existing_data.phase0_sentinel")) == 42
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())
