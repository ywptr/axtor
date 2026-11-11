"""Request-independent scoped persistence. Caller owns transaction/commit.

Reference registration is an operator responsibility; this module never registers
unknown tenants, applications or workspaces. No HTTP binding exists in Phase 1A.
"""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from axtor.core.context import ServiceClaims, VerifiedServiceContext
from axtor.persistence.models import (
    PolicyProfile,
    TenantApplication,
    TenantReference,
    WorkspaceReference,
)


class InvalidContext(ValueError):
    pass


class UnknownScope(LookupError):
    pass


class ProfileNotFound(LookupError):
    pass


async def _scope(session: AsyncSession, context: VerifiedServiceContext) -> ServiceClaims:
    if not isinstance(context, VerifiedServiceContext):
        raise InvalidContext("Verified service context required")
    claims = context.verified_claims()
    if not isinstance(claims, ServiceClaims):
        raise InvalidContext("Verified claims required")
    if await session.get(TenantReference, claims.tenant_id) is None:
        raise UnknownScope("Unknown scope")
    if claims.application_id is not None:
        key = (claims.tenant_id, claims.application_id)
        if await session.get(TenantApplication, key) is None:
            raise UnknownScope("Unknown scope")
    if claims.workspace_id is not None:
        workspace_key = (claims.tenant_id, claims.application_id, claims.workspace_id)
        if await session.get(WorkspaceReference, workspace_key) is None:
            raise UnknownScope("Unknown scope")
    return claims


def _query(claims: ServiceClaims) -> Select[PolicyProfile]:
    query = select(PolicyProfile).where(
        PolicyProfile.tenant_id == claims.tenant_id,
        PolicyProfile.application_id.is_not_distinct_from(claims.application_id),
        PolicyProfile.workspace_id.is_not_distinct_from(claims.workspace_id),
    )
    if claims.policy_profile is not None:
        query = query.where(PolicyProfile.name == claims.policy_profile)
    return query


async def list_profiles(
    session: AsyncSession, context: VerifiedServiceContext
) -> list[PolicyProfile]:
    claims = await _scope(session, context)
    return list((await session.scalars(_query(claims))).all())


async def get_profile(
    session: AsyncSession, context: VerifiedServiceContext, profile_id: UUID
) -> PolicyProfile:
    claims = await _scope(session, context)
    result = await session.scalar(_query(claims).where(PolicyProfile.profile_id == profile_id))
    if result is None:
        raise ProfileNotFound("Profile not found")
    return result


async def create_profile(
    session: AsyncSession, context: VerifiedServiceContext, name: str, description: str = ""
) -> PolicyProfile:
    claims = await _scope(session, context)
    if claims.policy_profile is not None and claims.policy_profile != name:
        raise InvalidContext("Profile outside verified scope")
    profile = PolicyProfile(
        tenant_id=claims.tenant_id,
        application_id=claims.application_id,
        workspace_id=claims.workspace_id,
        name=name,
        description=description,
    )
    session.add(profile)
    await session.flush()
    return profile


async def update_profile(
    session: AsyncSession, context: VerifiedServiceContext, profile_id: UUID, description: str
) -> PolicyProfile:
    profile = await get_profile(session, context, profile_id)
    profile.description = description
    await session.flush()
    return profile


async def delete_profile(
    session: AsyncSession, context: VerifiedServiceContext, profile_id: UUID
) -> None:
    profile = await get_profile(session, context, profile_id)
    await session.delete(profile)
    await session.flush()
