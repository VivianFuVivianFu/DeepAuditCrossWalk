"""Create tenant-scoped snapshots, atomic reviews and append-only audit events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_tenant_snapshots"
down_revision = None
branch_labels = None
depends_on = None

DOCUMENT_TABLES = (
    "questionnaires",
    "routing_snapshots",
    "use_cases",
    "policies",
    "assessments",
    "gaps",
    "mappings",
)


def upgrade():
    document_type = sa.JSON().with_variant(JSONB(), "postgresql")
    for name in DOCUMENT_TABLES:
        extra = []
        if name == "assessments":
            extra.append(sa.Column("kind", sa.String(32), nullable=False))
        if name == "gaps":
            extra.extend(
                [
                    sa.Column("assessment_id", sa.Text, nullable=False),
                    sa.Column("revision", sa.Integer, nullable=False),
                    sa.ForeignKeyConstraint(
                        ["tenant_id", "assessment_id"],
                        ["assessments.tenant_id", "assessments.object_id"],
                    ),
                    sa.CheckConstraint("revision >= 1", name="gaps_positive_revision"),
                ]
            )
        op.create_table(
            name,
            sa.Column("tenant_id", sa.String(128), primary_key=True),
            sa.Column("object_id", sa.Text, primary_key=True),
            sa.Column("payload", document_type, nullable=False),
            *extra,
        )
    op.create_index("gaps_assessment_idx", "gaps", ["tenant_id", "assessment_id"])
    op.create_table(
        "audit_events",
        sa.Column(
            "event_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("payload", document_type, nullable=False),
    )
    op.create_index(
        "audit_events_tenant_idx", "audit_events", ["tenant_id", "event_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        for name in (*DOCUMENT_TABLES, "audit_events"):
            # Identifiers are migration constants, never user input.
            op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
            predicate = (
                "tenant_id = nullif(current_setting('crosswalk.tenant_id', true), '')"
            )
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{name}" USING ({predicate}) WITH CHECK ({predicate})'
            )
        op.execute("""
            CREATE FUNCTION crosswalk_audit_append_only() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                RAISE EXCEPTION 'Crosswalk audit events are append-only';
            END; $$
        """)
        op.execute("""
            CREATE TRIGGER audit_events_append_only
            BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
            FOR EACH STATEMENT EXECUTE FUNCTION crosswalk_audit_append_only()
        """)


def downgrade():
    for name in reversed((*DOCUMENT_TABLES, "audit_events")):
        op.drop_table(name)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION crosswalk_audit_append_only()")
