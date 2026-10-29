"""Transactional PostgreSQL repository with tenant-qualified keys and forced RLS.

SQLite exercises the repository contract in fast tests; it is rejected by
production startup. PostgreSQL integration tests verify the actual RLS boundary.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import schema
from .catalog import load_aiaf_question_bank
from .database import check_schema, create_database_engine
from .models import (
    BankingUseCase,
    CoverageAssessment,
    GapRecord,
    MappingDecision,
    PolicyGapAssessment,
    PolicyPack,
    QuestionBank,
    QuestionRoutingSnapshot,
)
from .store import ConflictError, NotFoundError, StorageUnavailable


def assessment_gaps(assessment):
    return list(assessment.gaps)


class SQLTenantStore:
    def __init__(self, url: str, *, production: bool = False):
        self.engine = create_database_engine(url)
        self.is_durable = self.engine.dialect.name == "postgresql"
        self.production = production
        self._default_questionnaire = load_aiaf_question_bank()
        try:
            if production and not self.is_durable:
                raise StorageUnavailable("Production storage requires PostgreSQL")
            self.check_ready()
        except Exception:
            self.engine.dispose()
            raise

    def close(self):
        self.engine.dispose()

    def check_ready(self):
        try:
            with self.engine.connect() as connection:
                check_schema(connection)
                if self.engine.dialect.name == "postgresql":
                    role = connection.execute(
                        sa.text(
                            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                        )
                    ).one()
                    tables = connection.execute(
                        sa.text("""
                        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                               c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user) AS owns
                        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = current_schema() AND c.relname IN :names
                    """).bindparams(sa.bindparam("names", expanding=True)),
                        {"names": schema.TENANT_TABLES},
                    ).all()
                    if len(tables) != len(schema.TENANT_TABLES) or any(
                        not row.relrowsecurity or not row.relforcerowsecurity
                        for row in tables
                    ):
                        raise StorageUnavailable(
                            "Database tenant policies are not enabled"
                        )
                    if self.production and (
                        role.rolsuper
                        or role.rolbypassrls
                        or any(row.owns for row in tables)
                    ):
                        raise StorageUnavailable(
                            "Production requires a non-owner runtime role without BYPASSRLS"
                        )
        except (SQLAlchemyError, RuntimeError):
            raise StorageUnavailable(
                "Database is unavailable, unsafe or requires migrations"
            ) from None

    @contextmanager
    def _transaction(self, tenant_id):
        if not tenant_id or not tenant_id.strip() or len(tenant_id) > 128:
            raise ValueError(
                "A non-empty tenant ID of at most 128 characters is required"
            )
        try:
            with self.engine.begin() as connection:
                if self.engine.dialect.name == "postgresql":
                    connection.execute(
                        sa.text(
                            "SELECT set_config('crosswalk.tenant_id', :tenant, true)"
                        ),
                        {"tenant": tenant_id},
                    )
                yield connection
        except IntegrityError:
            raise ConflictError(
                "Record conflicts with an existing snapshot or tenant relationship"
            ) from None
        except SQLAlchemyError:
            raise StorageUnavailable(
                "Database operation failed; no partial changes were committed"
            ) from None

    def _upsert(self, connection, table, tenant_id, object_id, payload, **extra):
        insert = (
            postgres_insert
            if self.engine.dialect.name == "postgresql"
            else sqlite_insert
        )
        statement = insert(table).values(
            tenant_id=tenant_id, object_id=object_id, payload=payload, **extra
        )
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.tenant_id, table.c.object_id],
                set_={"payload": payload, **extra},
            )
        )

    def _record(
        self, connection, tenant_id, action, object_id, *, actor="api", detail=None
    ):
        connection.execute(
            schema.audit_events.insert().values(
                tenant_id=tenant_id,
                payload={
                    "at": datetime.now(timezone.utc).isoformat(),
                    "action": action,
                    "object_id": object_id,
                    "actor": actor,
                    "detail": detail or {},
                },
            )
        )

    @staticmethod
    def _check_tenant(tenant_id, record):
        if getattr(record, "tenant_id", tenant_id) != tenant_id:
            raise ValueError("Record tenant does not match the storage context")

    def _save(self, table, tenant_id, object_id, record, action):
        self._check_tenant(tenant_id, record)
        with self._transaction(tenant_id) as connection:
            self._upsert(
                connection, table, tenant_id, object_id, record.model_dump(mode="json")
            )
            self._record(connection, tenant_id, action, object_id)
        return record

    def _get(self, connection, table, tenant_id, object_id, model):
        value = connection.execute(
            sa.select(table.c.payload).where(
                table.c.tenant_id == tenant_id,
                table.c.object_id == object_id,
            )
        ).scalar_one_or_none()
        if value is None:
            raise NotFoundError("Record not found for this tenant")
        return model.model_validate(value)

    def _read(self, table, tenant_id, object_id, model):
        with self._transaction(tenant_id) as connection:
            return self._get(connection, table, tenant_id, object_id, model)

    def save_questionnaire(self, tenant_id, bank):
        return self._save(
            schema.questionnaires,
            tenant_id,
            bank.metadata.questionnaire_id,
            bank,
            "questionnaire.imported",
        )

    def get_questionnaire(self, tenant_id, questionnaire_id=None):
        if (
            questionnaire_id is None
            or questionnaire_id == self._default_questionnaire.metadata.questionnaire_id
        ):
            return self._default_questionnaire.model_copy(deep=True)
        return self._read(
            schema.questionnaires, tenant_id, questionnaire_id, QuestionBank
        )

    def save_routing_snapshot(self, tenant_id, snapshot):
        return self._save(
            schema.routing_snapshots,
            tenant_id,
            snapshot.snapshot_id,
            snapshot,
            "questionnaire.routed",
        )

    def get_routing_snapshot(self, tenant_id, snapshot_id):
        return self._read(
            schema.routing_snapshots, tenant_id, snapshot_id, QuestionRoutingSnapshot
        )

    def save_use_case(self, tenant_id, use_case):
        if not use_case.use_case_id:
            raise ValueError("use_case_id is required before storage")
        return self._save(
            schema.use_cases,
            tenant_id,
            use_case.use_case_id,
            use_case,
            "use_case.created",
        )

    def get_use_case(self, tenant_id, use_case_id):
        return self._read(schema.use_cases, tenant_id, use_case_id, BankingUseCase)

    def save_policy(self, tenant_id, policy):
        return self._save(
            schema.policies, tenant_id, policy.policy_pack_id, policy, "policy.imported"
        )

    def get_policy(self, tenant_id, policy_pack_id):
        return self._read(schema.policies, tenant_id, policy_pack_id, PolicyPack)

    def save_assessment(self, tenant_id, assessment):
        self._check_tenant(tenant_id, assessment)
        kind = (
            "coverage" if isinstance(assessment, CoverageAssessment) else "policy_gaps"
        )
        with self._transaction(tenant_id) as connection:
            connection.execute(
                schema.assessments.insert().values(
                    tenant_id=tenant_id,
                    object_id=assessment.assessment_id,
                    kind=kind,
                    payload=assessment.model_dump(mode="json"),
                )
            )
            for gap in assessment_gaps(assessment):
                connection.execute(
                    schema.gaps.insert().values(
                        tenant_id=tenant_id,
                        object_id=gap.gap_id,
                        assessment_id=assessment.assessment_id,
                        revision=gap.revision,
                        payload=gap.model_dump(mode="json"),
                    )
                )
            self._record(
                connection, tenant_id, "assessment.created", assessment.assessment_id
            )
        return assessment

    def get_assessment(self, tenant_id, assessment_id):
        with self._transaction(tenant_id) as connection:
            row = (
                connection.execute(
                    sa.select(schema.assessments).where(
                        schema.assessments.c.tenant_id == tenant_id,
                        schema.assessments.c.object_id == assessment_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NotFoundError("Assessment not found for this tenant")
            model = (
                CoverageAssessment if row["kind"] == "coverage" else PolicyGapAssessment
            )
            assessment = model.model_validate(row["payload"])
            current = {
                item["object_id"]: GapRecord.model_validate(item["payload"])
                for item in connection.execute(
                    sa.select(schema.gaps).where(
                        schema.gaps.c.tenant_id == tenant_id,
                        schema.gaps.c.assessment_id == assessment_id,
                    )
                ).mappings()
            }
            fields = (
                ["gaps"]
                if model is CoverageAssessment
                else [
                    "policy_gaps",
                    "questionnaire_gaps",
                    "control_conflicts",
                    "implementation_evidence_gaps",
                ]
            )
            return assessment.model_copy(
                update={
                    field: [
                        current.get(gap.gap_id, gap)
                        for gap in getattr(assessment, field)
                    ]
                    for field in fields
                }
            )

    def gaps_for_assessment(self, tenant_id, assessment_id):
        return assessment_gaps(self.get_assessment(tenant_id, assessment_id))

    def get_gap(self, tenant_id, gap_id):
        return self._read(schema.gaps, tenant_id, gap_id, GapRecord)

    def save_gap(self, tenant_id, gap, actor):
        updated = gap.model_copy(update={"revision": gap.revision + 1})
        with self._transaction(tenant_id) as connection:
            result = connection.execute(
                schema.gaps.update()
                .where(
                    schema.gaps.c.tenant_id == tenant_id,
                    schema.gaps.c.object_id == gap.gap_id,
                    schema.gaps.c.revision == gap.revision,
                )
                .values(
                    payload=updated.model_dump(mode="json"), revision=updated.revision
                )
            )
            if result.rowcount != 1:
                raise ConflictError(
                    "Gap changed or is unavailable; refresh before reviewing again"
                )
            self._record(
                connection,
                tenant_id,
                f"gap.{updated.status}",
                gap.gap_id,
                actor=actor,
                detail=updated.model_dump(mode="json"),
            )
        return updated

    def save_mapping(self, tenant_id, mapping, actor):
        # Canonical JSON avoids collisions from delimiter characters in IDs.
        key = [
            getattr(mapping, field) or ""
            for field in (
                "obligation_id",
                "facet",
                "question_id",
                "questionnaire_id",
                "questionnaire_sha256",
                "regulatory_pack_id",
                "regulatory_pack_version",
            )
        ]
        object_id = hashlib.sha256(
            json.dumps(key, ensure_ascii=True).encode()
        ).hexdigest()
        with self._transaction(tenant_id) as connection:
            self._upsert(
                connection,
                schema.mappings,
                tenant_id,
                object_id,
                mapping.model_dump(mode="json"),
            )
            self._record(
                connection,
                tenant_id,
                f"mapping.{mapping.review_status.value}",
                object_id,
                actor=actor,
                detail=mapping.model_dump(mode="json"),
            )
        return mapping

    def mappings(self, tenant_id, **filters):
        allowed = {
            "questionnaire_id",
            "questionnaire_sha256",
            "regulatory_pack_id",
            "regulatory_pack_version",
        }
        if set(filters) - allowed:
            raise ValueError("Unknown mapping filter")
        with self._transaction(tenant_id) as connection:
            # Filter on JSON in SQL so a version-bound lookup need not load a
            # tenant's complete history of approved/rejected mappings.
            statement = sa.select(schema.mappings.c.payload).where(
                schema.mappings.c.tenant_id == tenant_id
            )
            for field, value in filters.items():
                if value is not None:
                    statement = statement.where(
                        schema.mappings.c.payload[field].as_string() == value
                    )
            return [
                MappingDecision.model_validate(item)
                for item in connection.execute(statement).scalars()
            ]

    def audit_events(self, tenant_id):
        with self._transaction(tenant_id) as connection:
            return list(
                connection.execute(
                    sa.select(schema.audit_events.c.payload)
                    .where(
                        schema.audit_events.c.tenant_id == tenant_id,
                    )
                    .order_by(schema.audit_events.c.event_id)
                ).scalars()
            )
