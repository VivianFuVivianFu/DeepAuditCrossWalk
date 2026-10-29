"""Relational envelopes for versioned, validated domain snapshots.

Tenant IDs are part of every primary/foreign key. JSON documents retain the
engine's complete source/version metadata without a lossy second domain model.
Schema changes must have an Alembic revision; startup never creates tables.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()
document_type = sa.JSON().with_variant(JSONB(), "postgresql")


def document_table(name, *columns, **kwargs):
    return sa.Table(
        name,
        metadata,
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.Text, primary_key=True),
        sa.Column("payload", document_type, nullable=False),
        *columns,
        **kwargs,
    )


questionnaires = document_table("questionnaires")
routing_snapshots = document_table("routing_snapshots")
use_cases = document_table("use_cases")
policies = document_table("policies")
assessments = document_table(
    "assessments", sa.Column("kind", sa.String(32), nullable=False)
)
gaps = document_table(
    "gaps",
    sa.Column("assessment_id", sa.Text, nullable=False),
    sa.Column("revision", sa.Integer, nullable=False),
    sa.ForeignKeyConstraint(
        ["tenant_id", "assessment_id"],
        ["assessments.tenant_id", "assessments.object_id"],
    ),
    sa.CheckConstraint("revision >= 1", name="gaps_positive_revision"),
)
sa.Index("gaps_assessment_idx", gaps.c.tenant_id, gaps.c.assessment_id)
mappings = document_table("mappings")
audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column(
        "event_id",
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        primary_key=True,
    ),
    sa.Column("tenant_id", sa.String(128), nullable=False),
    sa.Column("payload", document_type, nullable=False),
)
sa.Index("audit_events_tenant_idx", audit_events.c.tenant_id, audit_events.c.event_id)
TENANT_TABLES = tuple(metadata.tables)
