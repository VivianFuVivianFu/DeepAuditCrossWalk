"""Tenant-scoped in-memory repository for the MVP.

The engines are storage-agnostic.  This repository provides a runnable local
MVP and an explicit seam for a PostgreSQL/Supabase implementation.  It is not
durable across processes or restarts.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from .catalog import load_aiaf_question_bank
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


class NotFoundError(KeyError):
    pass


class TenantStore:
    # The API uses this capability flag rather than assuming that a configured
    # DATABASE_URL makes Crosswalk records durable.  The SQLModel contract in
    # A PostgreSQL repository is a future extension; DATABASE_URL alone must
    # never be interpreted as durable storage being available.
    is_durable = False

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._questionnaires: Dict[str, Dict[str, QuestionBank]] = {}
        self._routing_snapshots: Dict[str, Dict[str, QuestionRoutingSnapshot]] = {}
        self._use_cases: Dict[str, Dict[str, BankingUseCase]] = {}
        self._policies: Dict[str, Dict[str, PolicyPack]] = {}
        self._assessments: Dict[
            str, Dict[str, CoverageAssessment | PolicyGapAssessment]
        ] = {}
        self._gaps: Dict[str, Dict[str, GapRecord]] = {}
        self._gap_assessments: Dict[str, Dict[str, str]] = {}
        self._mappings: Dict[str, Dict[tuple[str, ...], MappingDecision]] = {}
        self._audit_events: Dict[str, List[Dict[str, Any]]] = {}
        self._default_questionnaire = load_aiaf_question_bank()

    def _bucket(
        self, registry: Dict[str, Dict[str, Any]], tenant_id: str
    ) -> Dict[str, Any]:
        return registry.setdefault(tenant_id, {})

    def _record(
        self, tenant_id: str, action: str, object_id: str, actor: str = "api"
    ) -> None:
        self._audit_events.setdefault(tenant_id, []).append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "object_id": object_id,
                "actor": actor,
            }
        )

    def save_questionnaire(self, tenant_id: str, bank: QuestionBank) -> QuestionBank:
        with self._lock:
            self._bucket(self._questionnaires, tenant_id)[
                bank.metadata.questionnaire_id
            ] = bank
            self._record(
                tenant_id, "questionnaire.imported", bank.metadata.questionnaire_id
            )
        return bank

    def get_questionnaire(
        self, tenant_id: str, questionnaire_id: str | None = None
    ) -> QuestionBank:
        if (
            questionnaire_id is None
            or questionnaire_id == self._default_questionnaire.metadata.questionnaire_id
        ):
            return self._default_questionnaire
        try:
            return self._questionnaires[tenant_id][questionnaire_id]
        except KeyError as exc:
            raise NotFoundError("Questionnaire not found for this tenant") from exc

    def save_routing_snapshot(
        self, tenant_id: str, snapshot: QuestionRoutingSnapshot
    ) -> QuestionRoutingSnapshot:
        with self._lock:
            self._bucket(self._routing_snapshots, tenant_id)[snapshot.snapshot_id] = (
                snapshot
            )
            self._record(tenant_id, "questionnaire.routed", snapshot.snapshot_id)
        return snapshot

    def get_routing_snapshot(
        self, tenant_id: str, snapshot_id: str
    ) -> QuestionRoutingSnapshot:
        try:
            return self._routing_snapshots[tenant_id][snapshot_id]
        except KeyError as exc:
            raise NotFoundError(
                "Question routing snapshot not found for this tenant"
            ) from exc

    def save_use_case(self, tenant_id: str, use_case: BankingUseCase) -> BankingUseCase:
        if not use_case.use_case_id:
            raise ValueError("use_case_id is required before storage")
        with self._lock:
            self._bucket(self._use_cases, tenant_id)[use_case.use_case_id] = use_case
            self._record(tenant_id, "use_case.created", use_case.use_case_id)
        return use_case

    def get_use_case(self, tenant_id: str, use_case_id: str) -> BankingUseCase:
        try:
            return self._use_cases[tenant_id][use_case_id]
        except KeyError as exc:
            raise NotFoundError("Use case not found for this tenant") from exc

    def save_policy(self, tenant_id: str, policy: PolicyPack) -> PolicyPack:
        with self._lock:
            self._bucket(self._policies, tenant_id)[policy.policy_pack_id] = policy
            self._record(tenant_id, "policy.imported", policy.policy_pack_id)
        return policy

    def get_policy(self, tenant_id: str, policy_pack_id: str) -> PolicyPack:
        try:
            return self._policies[tenant_id][policy_pack_id]
        except KeyError as exc:
            raise NotFoundError("Policy pack not found for this tenant") from exc

    def save_assessment(
        self, tenant_id: str, assessment: CoverageAssessment | PolicyGapAssessment
    ) -> CoverageAssessment | PolicyGapAssessment:
        with self._lock:
            self._bucket(self._assessments, tenant_id)[assessment.assessment_id] = (
                assessment
            )
            assessment_gaps: Sequence[GapRecord] = []
            if isinstance(assessment, PolicyGapAssessment):
                assessment_gaps = [
                    *assessment.policy_gaps,
                    *assessment.questionnaire_gaps,
                    *assessment.control_conflicts,
                    *assessment.implementation_evidence_gaps,
                ]
            elif isinstance(assessment, CoverageAssessment):
                assessment_gaps = assessment.gaps
            gap_bucket = self._bucket(self._gaps, tenant_id)
            gap_assessment_bucket = self._bucket(self._gap_assessments, tenant_id)
            for gap in assessment_gaps:
                gap_bucket[gap.gap_id] = gap
                gap_assessment_bucket[gap.gap_id] = assessment.assessment_id
            self._record(tenant_id, "assessment.created", assessment.assessment_id)
        return assessment

    def get_assessment(
        self, tenant_id: str, assessment_id: str
    ) -> CoverageAssessment | PolicyGapAssessment:
        with self._lock:
            try:
                assessment = self._assessments[tenant_id][assessment_id]
            except KeyError as exc:
                raise NotFoundError("Assessment not found for this tenant") from exc
            refreshed = self._refresh_assessment_gaps(tenant_id, assessment)
            self._assessments[tenant_id][assessment_id] = refreshed
            return refreshed

    def _refresh_assessment_gaps(
        self,
        tenant_id: str,
        assessment: CoverageAssessment | PolicyGapAssessment,
    ) -> CoverageAssessment | PolicyGapAssessment:
        current = self._gaps.get(tenant_id, {})

        def refreshed(items: Sequence[GapRecord]) -> List[GapRecord]:
            return [current.get(item.gap_id, item) for item in items]

        if isinstance(assessment, CoverageAssessment):
            return assessment.model_copy(update={"gaps": refreshed(assessment.gaps)})
        return assessment.model_copy(
            update={
                "policy_gaps": refreshed(assessment.policy_gaps),
                "questionnaire_gaps": refreshed(assessment.questionnaire_gaps),
                "control_conflicts": refreshed(assessment.control_conflicts),
                "implementation_evidence_gaps": refreshed(
                    assessment.implementation_evidence_gaps
                ),
            }
        )

    def gaps_for_assessment(
        self, tenant_id: str, assessment_id: str
    ) -> List[GapRecord]:
        assessment = self.get_assessment(tenant_id, assessment_id)
        if isinstance(assessment, CoverageAssessment):
            return list(assessment.gaps)
        return [
            *assessment.policy_gaps,
            *assessment.questionnaire_gaps,
            *assessment.control_conflicts,
            *assessment.implementation_evidence_gaps,
        ]

    def get_gap(self, tenant_id: str, gap_id: str) -> GapRecord:
        try:
            return self._gaps[tenant_id][gap_id]
        except KeyError as exc:
            raise NotFoundError("Gap not found for this tenant") from exc

    def save_gap(self, tenant_id: str, gap: GapRecord, actor: str) -> GapRecord:
        with self._lock:
            self._bucket(self._gaps, tenant_id)[gap.gap_id] = gap
            assessment_id = self._gap_assessments.get(tenant_id, {}).get(gap.gap_id)
            if assessment_id:
                assessment = self._assessments[tenant_id][assessment_id]
                self._assessments[tenant_id][assessment_id] = (
                    self._refresh_assessment_gaps(tenant_id, assessment)
                )
            self._record(tenant_id, f"gap.{gap.status}", gap.gap_id, actor=actor)
        return gap

    def save_mapping(
        self, tenant_id: str, mapping: MappingDecision, actor: str
    ) -> MappingDecision:
        key = (
            mapping.obligation_id,
            mapping.facet,
            mapping.question_id,
            mapping.questionnaire_id or "",
            mapping.questionnaire_sha256 or "",
            mapping.regulatory_pack_id or "",
            mapping.regulatory_pack_version or "",
        )
        with self._lock:
            self._bucket(self._mappings, tenant_id)[key] = mapping
            self._record(
                tenant_id,
                f"mapping.{mapping.review_status.value}",
                "|".join(key),
                actor=actor,
            )
        return mapping

    def mappings(
        self,
        tenant_id: str,
        *,
        questionnaire_id: str | None = None,
        questionnaire_sha256: str | None = None,
        regulatory_pack_id: str | None = None,
        regulatory_pack_version: str | None = None,
    ) -> List[MappingDecision]:
        mappings = list(self._mappings.get(tenant_id, {}).values())
        expected = {
            "questionnaire_id": questionnaire_id,
            "questionnaire_sha256": questionnaire_sha256,
            "regulatory_pack_id": regulatory_pack_id,
            "regulatory_pack_version": regulatory_pack_version,
        }
        return [
            mapping
            for mapping in mappings
            if all(
                value is None or getattr(mapping, field) == value
                for field, value in expected.items()
            )
        ]

    def audit_events(self, tenant_id: str) -> List[Dict[str, Any]]:
        return list(self._audit_events.get(tenant_id, []))


store = TenantStore()
