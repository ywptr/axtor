"""Canonical tenant references and scoped policy profiles."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("tenant_references", sa.Column("tenant_id", sa.Uuid(), primary_key=True))
    op.create_table(
        "consumer_applications",
        sa.Column("application_id", sa.String(100), primary_key=True),
        sa.CheckConstraint("btrim(application_id) <> ''"),
    )
    op.create_table(
        "tenant_applications",
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenant_references.tenant_id"), primary_key=True
        ),
        sa.Column(
            "application_id",
            sa.String(100),
            sa.ForeignKey("consumer_applications.application_id"),
            primary_key=True,
        ),
    )
    op.create_table(
        "workspace_references",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.String(100), primary_key=True),
        sa.Column("workspace_id", sa.String(200), primary_key=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["tenant_applications.tenant_id", "tenant_applications.application_id"],
        ),
        sa.CheckConstraint("btrim(workspace_id) <> ''"),
    )
    op.create_table(
        "policy_profiles",
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenant_references.tenant_id"), primary_key=True
        ),
        sa.Column("profile_id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.String(100)),
        sa.Column("workspace_id", sa.String(200)),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["tenant_applications.tenant_id", "tenant_applications.application_id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id", "workspace_id"],
            [
                "workspace_references.tenant_id",
                "workspace_references.application_id",
                "workspace_references.workspace_id",
            ],
        ),
        sa.CheckConstraint("workspace_id IS NULL OR application_id IS NOT NULL"),
        sa.CheckConstraint("btrim(name) <> ''"),
    )
    op.create_index(
        "uq_policy_tenant",
        "policy_profiles",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("application_id IS NULL"),
    )
    op.create_index(
        "uq_policy_application",
        "policy_profiles",
        ["tenant_id", "application_id", "name"],
        unique=True,
        postgresql_where=sa.text("application_id IS NOT NULL AND workspace_id IS NULL"),
    )
    op.create_index(
        "uq_policy_workspace",
        "policy_profiles",
        ["tenant_id", "application_id", "workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("workspace_id IS NOT NULL"),
    )
    # Identity updates are forbidden even when no dependent record exists.
    op.execute("""
        CREATE FUNCTION axtor_immutable_identity() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'reference identity is immutable' USING ERRCODE = '23514';
        END; $$
    """)
    for table, columns in (
        ("tenant_references", "tenant_id"),
        ("consumer_applications", "application_id"),
        ("tenant_applications", "tenant_id, application_id"),
        ("workspace_references", "tenant_id, application_id, workspace_id"),
        ("policy_profiles", "tenant_id, profile_id, application_id, workspace_id, name"),
    ):
        op.execute(
            f"CREATE TRIGGER immutable_identity BEFORE UPDATE OF {columns} ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION axtor_immutable_identity()"
        )


def downgrade() -> None:
    for table in (
        "policy_profiles",
        "workspace_references",
        "tenant_applications",
        "consumer_applications",
        "tenant_references",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION axtor_immutable_identity()")
