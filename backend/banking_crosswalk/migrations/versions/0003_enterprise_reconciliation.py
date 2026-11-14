"""Create enterprise requirement reconciliation and effective baseline tables with RLS.

Adds:
- reconciliation_decisions: versioned requirement reconciliation records (Stage A/B + human review)
- effective_baselines: composed Effective Assessment Baselines
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_enterprise_reconciliation"
down_revision = "0002_enterprise_policy_layer"
branch_labels = None
depends_on = None

RECONCILIATION_TABLES = (
    "reconciliation_decisions",
    "effective_baselines",
)


def upgrade():
    document_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "reconciliation_decisions",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.Text, primary_key=True),
        sa.Column("payload", document_type, nullable=False),
        sa.Column("baseline_id", sa.Text, nullable=False),
        sa.Column("clause_id", sa.Text, nullable=False),
        sa.Column("obligation_id", sa.Text, nullable=True),
    )
    op.create_index(
        "reconciliation_decisions_baseline_idx",
        "reconciliation_decisions",
        ["tenant_id", "baseline_id"],
    )

    op.create_table(
        "effective_baselines",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.Text, primary_key=True),
        sa.Column("payload", document_type, nullable=False),
        sa.Column("baseline_id", sa.Text, nullable=True),
    )
    op.create_index(
        "effective_baselines_baseline_idx",
        "effective_baselines",
        ["tenant_id", "baseline_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        predicate = (
            "tenant_id = nullif(current_setting('crosswalk.tenant_id', true), '')"
        )
        for name in RECONCILIATION_TABLES:
            op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{name}" USING ({predicate}) WITH CHECK ({predicate})'
            )


def downgrade():
    for name in reversed(RECONCILIATION_TABLES):
        op.drop_table(name)
