"""Internal trust boundary. Phase 1A deliberately supplies no context issuer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ServiceClaims:
    tenant_id: UUID
    calling_service: str
    originating_actor: str
    delegation: tuple[str, ...]
    application_id: str | None = None
    workspace_id: str | None = None
    policy_profile: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("Canonical tenant UUID required")
        values = (self.calling_service, self.originating_actor, *self.delegation)
        optional = (self.application_id, self.workspace_id, self.policy_profile)
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError("Identity and provenance must be nonempty strings")
        if not isinstance(self.delegation, tuple):
            raise ValueError("Immutable delegation required")
        if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in optional):
            raise ValueError("Invalid scope")
        if self.workspace_id is not None and self.application_id is None:
            raise ValueError("Workspace requires application")


class VerifiedServiceContext(ABC):
    """Implemented only by a future trusted verifier, never by request deserialization.

    Claims alone convey no authority. Python interfaces are not a sandbox against
    malicious in-process code. Test implementations live exclusively in tests.
    """

    @abstractmethod
    def verified_claims(self) -> ServiceClaims:
        """Return immutable claims after verification, including scope authority."""
        raise NotImplementedError
