"""Create enterprise policy layer tables with tenant-scoped isolation.

Adds:
- enterprise_policies: private tenant policy documents
- enterprise_clauses: extracted or curated enterprise clauses
- clause_control_mappings: mappings between enterprise clauses and Unified Controls
- enterprise_baselines: aggregations of enterprise policies forming a control baseline
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_enterprise_policy_layer"
down_revision = "0001_tenant_snapshots"
branch_labels = None
depends_on = None

ENTERPRISE_TABLES = (
    "enterprise_policies",
    "enterprise_clauses",
    "clause_control_mappings",
    "enterprise_baselines",
)


def upgrade():
    document_type = sa.JSON().with_variant(JSONB(), "postgresql")
    for name in ENTERPRISE_TABLES:
        extra = []
        if name == "enterprise_clauses":
            extra.append(sa.Column("policy_id", sa.Text, nullable=False))
        elif name == "clause_control_mappings":
            extra.extend(
                [
                    sa.Column("clause_id", sa.Text, nullable=False),
                    sa.Column("control_id", sa.Text, nullable=False),
                ]
            )
        op.create_table(
            name,
            sa.Column("tenant_id", sa.String(128), primary_key=True),
            sa.Column("object_id", sa.Text, primary_key=True),
            sa.Column("payload", document_type, nullable=False),
            *extra,
        )
    op.create_index(
        "enterprise_clauses_policy_idx", "enterprise_clauses", ["tenant_id", "policy_id"]
    )
    op.create_index(
        "clause_mappings_control_idx", "clause_control_mappings", ["tenant_id", "control_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        for name in ENTERPRISE_TABLES:
            op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
            predicate = (
                "tenant_id = nullif(current_setting('crosswalk.tenant_id', true), '')"
            )
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{name}" USING ({predicate}) WITH CHECK ({predicate})'
            )


def downgrade():
    for name in reversed(ENTERPRISE_TABLES):
        op.drop_table(name)

