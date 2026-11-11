"""Reference records are not tenant lifecycle, membership or entitlement records."""

from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from axtor.persistence.database import Base


class TenantReference(Base):
    __tablename__ = "tenant_references"
    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)  # Nexus supplied; no default


class ConsumerApplication(Base):
    __tablename__ = "consumer_applications"
    application_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    __table_args__ = (CheckConstraint("btrim(application_id) <> ''"),)


class TenantApplication(Base):
    __tablename__ = "tenant_applications"
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant_references.tenant_id"), primary_key=True
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("consumer_applications.application_id"), primary_key=True
    )


class WorkspaceReference(Base):
    __tablename__ = "workspace_references"
    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["tenant_applications.tenant_id", "tenant_applications.application_id"],
        ),
        CheckConstraint("btrim(workspace_id) <> ''"),
    )


class PolicyProfile(Base):
    __tablename__ = "policy_profiles"
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant_references.tenant_id"), primary_key=True
    )
    profile_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[str | None] = mapped_column(String(100))
    workspace_id: Mapped[str | None] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(1000), default="")
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["tenant_applications.tenant_id", "tenant_applications.application_id"],
        ),
        ForeignKeyConstraint(
            ["tenant_id", "application_id", "workspace_id"],
            [
                "workspace_references.tenant_id",
                "workspace_references.application_id",
                "workspace_references.workspace_id",
            ],
        ),
        CheckConstraint("workspace_id IS NULL OR application_id IS NOT NULL"),
        CheckConstraint("btrim(name) <> ''"),
        Index(
            "uq_policy_tenant",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("application_id IS NULL"),
        ),
        Index(
            "uq_policy_application",
            "tenant_id",
            "application_id",
            "name",
            unique=True,
            postgresql_where=text("application_id IS NOT NULL AND workspace_id IS NULL"),
        ),
        Index(
            "uq_policy_workspace",
            "tenant_id",
            "application_id",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("workspace_id IS NOT NULL"),
        ),
    )
