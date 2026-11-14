"""Tenant-scoped in-memory repository for the MVP.

The engines are storage-agnostic.  This repository provides a runnable local
MVP and an explicit seam for a PostgreSQL/Supabase implementation.  It is not
durable across processes or restarts.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .catalog import load_demo_questionnaire
from .models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    EffectiveAssessmentBaseline,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    BankingUseCase,
    CoverageAssessment,
    GapRecord,
    MappingDecision,
    PolicyGapAssessment,
    PolicyPack,
    QuestionBank,
    QuestionRoutingSnapshot,
    ReconciliationDecision,
)


class NotFoundError(KeyError):
    pass


class StorageUnavailable(RuntimeError):
    """Sanitised storage failure; never expose driver/connection details."""


class ConflictError(RuntimeError):
    """The record changed or an immutable snapshot already exists."""


class TenantStore:
    # Production permits this store only with an explicit demo override.
    is_durable = False

    def check_ready(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._questionnaires: Dict[str, Dict[str, QuestionBank]] = {}
        self._routing_snapshots: Dict[str, Dict[str, QuestionRoutingSnapshot]] = {}
        self._use_cases: Dict[str, Dict[str, BankingUseCase]] = {}
        self._policies: Dict[str, Dict[str, PolicyPack]] = {}
        self._enterprise_policies: Dict[str, Dict[str, EnterprisePolicy]] = {}
        self._enterprise_clauses: Dict[str, Dict[str, EnterpriseClause]] = {}
        self._clause_mappings: Dict[str, Dict[str, ClauseControlMapping]] = {}
        self._enterprise_baselines: Dict[str, Dict[str, EnterpriseBaseline]] = {}
        self._reconciliation_decisions: Dict[str, Dict[str, ReconciliationDecision]] = {}
        self._effective_baselines: Dict[str, Dict[str, EffectiveAssessmentBaseline]] = {}
        self._assessments: Dict[
            str, Dict[str, CoverageAssessment | PolicyGapAssessment]
        ] = {}
        self._gaps: Dict[str, Dict[str, GapRecord]] = {}
        self._gap_assessments: Dict[str, Dict[str, str]] = {}
        self._mappings: Dict[str, Dict[tuple[str, ...], MappingDecision]] = {}
        self._audit_events: Dict[str, List[Dict[str, Any]]] = {}
        self._default_questionnaire = load_demo_questionnaire()

    def _bucket(
        self, registry: Dict[str, Dict[str, Any]], tenant_id: str
    ) -> Dict[str, Any]:
        return registry.setdefault(tenant_id, {})

    def _record(
        self, tenant_id: str, action: str, object_id: str, actor: str = "api", detail: Optional[Dict[str, Any]] = None
    ) -> None:
        self._audit_events.setdefault(tenant_id, []).append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "object_id": object_id,
                "actor": actor,
                "detail": detail or {},
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

    def list_questionnaires(self, tenant_id: str) -> List[QuestionBank]:
        with self._lock:
            return list(self._questionnaires.get(tenant_id, {}).values())

    def get_tenant_questionnaire(
        self, tenant_id: str, questionnaire_id: str
    ) -> QuestionBank:
        with self._lock:
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
            current = self.get_gap(tenant_id, gap.gap_id)
            if current.revision != gap.revision:
                raise ConflictError("Gap changed; refresh it before reviewing again")
            gap = gap.model_copy(update={"revision": gap.revision + 1})
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



    # --- Enterprise Regulatory & Policy Layer Methods ---

    def save_enterprise_policy(
        self, tenant_id: str, policy: EnterprisePolicy
    ) -> EnterprisePolicy:
        for existing in self._enterprise_policies.get(tenant_id, {}).values():
            if existing.file_sha256 == policy.file_sha256 and existing.policy_id != policy.policy_id:
                warning = f"Identical policy content already uploaded as '{existing.name}' (version {existing.version})."
                if warning not in policy.warnings:
                    policy.warnings.append(warning)
        self._bucket(self._enterprise_policies, tenant_id)[policy.policy_id] = policy
        self._record(tenant_id, "enterprise_policy.saved", policy.policy_id)
        for clause in policy.clauses:
            self._bucket(self._enterprise_clauses, tenant_id)[clause.clause_id] = clause
            for mapping in clause.control_mappings:
                self._bucket(self._clause_mappings, tenant_id)[mapping.mapping_id] = mapping
        return policy

    def get_enterprise_policy(
        self, tenant_id: str, policy_id: str
    ) -> EnterprisePolicy:
        try:
            return self._enterprise_policies[tenant_id][policy_id]
        except KeyError as exc:
            raise NotFoundError("Enterprise policy not found for this tenant") from exc

    def list_enterprise_policies(self, tenant_id: str) -> List[EnterprisePolicy]:
        return list(self._enterprise_policies.get(tenant_id, {}).values())

    def delete_enterprise_policy(self, tenant_id: str, policy_id: str) -> None:
        if tenant_id in self._enterprise_policies and policy_id in self._enterprise_policies[tenant_id]:
            policy = self._enterprise_policies[tenant_id].pop(policy_id)
            if tenant_id in self._enterprise_clauses:
                for clause in policy.clauses:
                    self._enterprise_clauses[tenant_id].pop(clause.clause_id, None)
            self._record(tenant_id, "enterprise_policy.deleted", policy_id)

    def get_enterprise_clause(
        self, tenant_id: str, clause_id: str
    ) -> EnterpriseClause:
        try:
            return self._enterprise_clauses[tenant_id][clause_id]
        except KeyError as exc:
            raise NotFoundError("Enterprise clause not found for this tenant") from exc

    def list_enterprise_clauses(
        self, tenant_id: str, policy_id: Optional[str] = None
    ) -> List[EnterpriseClause]:
        clauses = list(self._enterprise_clauses.get(tenant_id, {}).values())
        if policy_id:
            clauses = [c for c in clauses if c.policy_id == policy_id]
        return clauses

    def update_clause_review(
        self,
        tenant_id: str,
        clause_id: str,
        status: ClauseReviewStatus,
        actor: str,
        role: str,
        mappings: Optional[List[ClauseControlMapping]] = None,
        review_comment: Optional[str] = None,
    ) -> EnterpriseClause:
        clause = self.get_enterprise_clause(tenant_id, clause_id).model_copy(deep=True)
        clause.review_status = status
        clause.reviewer_actor = actor
        clause.reviewer_role = role
        if review_comment is not None:
            clause.review_comment = review_comment
        clause.reviewed_at = datetime.now(timezone.utc)
        if mappings is not None:
            for m in mappings:
                if m.tenant_id != tenant_id or m.clause_id != clause_id:
                    raise NotFoundError("Control mapping does not belong to this tenant or clause")
            clause.control_mappings = [m.model_copy(deep=True) for m in mappings]
            for m in clause.control_mappings:
                self._bucket(self._clause_mappings, tenant_id)[m.mapping_id] = m
        self._bucket(self._enterprise_clauses, tenant_id)[clause_id] = clause
        if tenant_id in self._enterprise_policies and clause.policy_id in self._enterprise_policies[tenant_id]:
            pol = self._enterprise_policies[tenant_id][clause.policy_id]
            for idx, c in enumerate(pol.clauses):
                if c.clause_id == clause_id:
                    pol.clauses[idx] = clause
                    break
        self._record(tenant_id, "clause.reviewed", clause_id, actor=actor, detail={"status": status.value})
        return clause

    def update_clause_mapping_review(
        self,
        tenant_id: str,
        clause_id: str,
        mapping_id: str,
        status: ClauseReviewStatus,
        actor: str,
        role: str,
        relationship: Optional[Any] = None,
        mapped_facets: Optional[List[str]] = None,
        review_comment: Optional[str] = None,
    ) -> ClauseControlMapping:
        clause = self.get_enterprise_clause(tenant_id, clause_id).model_copy(deep=True)
        target_mapping: Optional[ClauseControlMapping] = None
        for idx, m in enumerate(clause.control_mappings):
            if m.mapping_id == mapping_id:
                if m.tenant_id != tenant_id or m.clause_id != clause_id:
                    raise NotFoundError("Control mapping not found for this tenant or clause")
                updated_m = m.model_copy(deep=True)
                updated_m.review_status = status
                updated_m.reviewer_actor = actor
                updated_m.reviewer_role = role
                if review_comment is not None:
                    updated_m.review_comment = review_comment
                if relationship is not None:
                    updated_m.relationship = relationship
                if mapped_facets is not None:
                    updated_m.mapped_facets = list(mapped_facets)
                updated_m.reviewed_at = datetime.now(timezone.utc)
                clause.control_mappings[idx] = updated_m
                target_mapping = updated_m
                break
        if target_mapping is None:
            raise NotFoundError("Control mapping not found for this clause")
        self._bucket(self._clause_mappings, tenant_id)[mapping_id] = target_mapping
        self._bucket(self._enterprise_clauses, tenant_id)[clause_id] = clause
        if tenant_id in self._enterprise_policies and clause.policy_id in self._enterprise_policies[tenant_id]:
            pol = self._enterprise_policies[tenant_id][clause.policy_id]
            for idx, c in enumerate(pol.clauses):
                if c.clause_id == clause_id:
                    pol.clauses[idx] = clause
                    break
        self._record(
            tenant_id,
            "clause_mapping.reviewed",
            mapping_id,
            actor=actor,
            detail={
                "clause_id": clause_id,
                "control_id": target_mapping.control_id,
                "status": status.value,
            },
        )
        return target_mapping

    def save_clause_mapping(
        self, tenant_id: str, mapping: ClauseControlMapping
    ) -> ClauseControlMapping:
        self._bucket(self._clause_mappings, tenant_id)[mapping.mapping_id] = mapping
        self._record(tenant_id, "clause_mapping.saved", mapping.mapping_id)
        return mapping

    def list_clause_mappings(
        self, tenant_id: str, clause_id: Optional[str] = None, control_id: Optional[str] = None
    ) -> List[ClauseControlMapping]:
        items = list(self._clause_mappings.get(tenant_id, {}).values())
        if clause_id:
            items = [m for m in items if m.clause_id == clause_id]
        if control_id:
            items = [m for m in items if m.control_id == control_id]
        return items

    def save_enterprise_baseline(
        self, tenant_id: str, baseline: EnterpriseBaseline
    ) -> EnterpriseBaseline:
        bucket = self._bucket(self._enterprise_baselines, tenant_id)
        if baseline.baseline_id in bucket:
            existing = bucket[baseline.baseline_id]
            if (
                existing.revision == baseline.revision
                and existing.baseline_sha256 is not None
                and existing.baseline_sha256 != baseline.baseline_sha256
            ):
                raise ConflictError("Enterprise baseline is immutable; increment revision to update.")
        bucket[baseline.baseline_id] = baseline
        self._record(tenant_id, "enterprise_baseline.saved", baseline.baseline_id)
        return baseline

    def get_enterprise_baseline(
        self, tenant_id: str, baseline_id: str
    ) -> EnterpriseBaseline:
        try:
            return self._enterprise_baselines[tenant_id][baseline_id]
        except KeyError as exc:
            raise NotFoundError("Enterprise baseline not found for this tenant") from exc

    def list_enterprise_baselines(self, tenant_id: str) -> List[EnterpriseBaseline]:
        return list(self._enterprise_baselines.get(tenant_id, {}).values())

    def save_reconciliation_decision(
        self,
        tenant_id: str,
        decision: ReconciliationDecision,
        actor: str = "system",
    ) -> ReconciliationDecision:
        if decision.tenant_id != tenant_id:
            raise ValueError("Reconciliation decision tenant mismatch")
        self._bucket(self._reconciliation_decisions, tenant_id)[
            decision.reconciliation_id
        ] = decision
        self._record(
            tenant_id,
            "reconciliation.saved",
            decision.reconciliation_id,
            actor=actor,
            detail={
                "baseline_id": decision.enterprise_baseline_id,
                "clause_id": decision.enterprise_clause_id,
                "obligation_id": decision.external_obligation_id,
                "status": decision.decision_status.value,
                "relationship": (
                    decision.approved_relationship.value
                    if decision.approved_relationship
                    else decision.validated_relationship.value
                ),
            },
        )
        return decision

    def save_reconciliation_decisions(
        self,
        tenant_id: str,
        decisions: Sequence[ReconciliationDecision],
        actor: str = "system",
    ) -> List[ReconciliationDecision]:
        saved: List[ReconciliationDecision] = []
        for d in decisions:
            saved.append(self.save_reconciliation_decision(tenant_id, d, actor=actor))
        return saved

    def get_reconciliation_decision(
        self, tenant_id: str, reconciliation_id: str
    ) -> ReconciliationDecision:
        try:
            return self._reconciliation_decisions[tenant_id][reconciliation_id]
        except KeyError as exc:
            raise NotFoundError(
                "Reconciliation decision not found for this tenant"
            ) from exc

    def list_reconciliation_decisions(
        self,
        tenant_id: str,
        baseline_id: Optional[str] = None,
        clause_id: Optional[str] = None,
        obligation_id: Optional[str] = None,
    ) -> List[ReconciliationDecision]:
        items = list(self._reconciliation_decisions.get(tenant_id, {}).values())
        if baseline_id is not None:
            items = [d for d in items if d.enterprise_baseline_id == baseline_id]
        if clause_id is not None:
            items = [d for d in items if d.enterprise_clause_id == clause_id]
        if obligation_id is not None:
            items = [d for d in items if d.external_obligation_id == obligation_id]
        return sorted(items, key=lambda x: x.reconciliation_id)

    def save_effective_baseline(
        self,
        tenant_id: str,
        effective_baseline: EffectiveAssessmentBaseline,
        actor: str = "system",
    ) -> EffectiveAssessmentBaseline:
        if effective_baseline.tenant_id != tenant_id:
            raise ValueError("Effective baseline tenant mismatch")
        self._bucket(self._effective_baselines, tenant_id)[
            effective_baseline.effective_baseline_id
        ] = effective_baseline
        self._record(
            tenant_id,
            "effective_baseline.saved",
            effective_baseline.effective_baseline_id,
            actor=actor,
            detail={
                "enterprise_baseline_id": effective_baseline.enterprise_baseline_id,
                "effective_baseline_sha256": effective_baseline.effective_baseline_sha256,
            },
        )
        return effective_baseline

    def get_effective_baseline(
        self, tenant_id: str, effective_baseline_id: str
    ) -> EffectiveAssessmentBaseline:
        try:
            return self._effective_baselines[tenant_id][effective_baseline_id]
        except KeyError as exc:
            raise NotFoundError(
                "Effective baseline not found for this tenant"
            ) from exc

    def list_effective_baselines(
        self, tenant_id: str, baseline_id: Optional[str] = None
    ) -> List[EffectiveAssessmentBaseline]:
        items = list(self._effective_baselines.get(tenant_id, {}).values())
        if baseline_id is not None:
            items = [
                b for b in items if b.enterprise_baseline_id == baseline_id
            ]
        return sorted(items, key=lambda x: x.effective_baseline_id)


class RepositoryHandle:
    """Keep imports stable while the ASGI lifespan selects one repository."""

    def __init__(self):
        self.repository = TenantStore()

    def __getattr__(self, name):
        return getattr(self.repository, name)

    def configure(self, database_url: str | None, *, production: bool) -> None:
        if not database_url:
            return
        try:
            from .sql_store import SQLTenantStore

            repository = SQLTenantStore(database_url, production=production)
        except Exception:
            raise StorageUnavailable(
                "Configured database is unavailable or unsafe. Check migrations and runtime role."
            ) from None
        self.repository.close()
        self.repository = repository

    def reset(self) -> None:
        self.repository.close()
        self.repository = TenantStore()


store = RepositoryHandle()
