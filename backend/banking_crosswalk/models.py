"""Typed domain model for the Banking Regulatory Crosswalk.

These models deliberately separate legal applicability, questionnaire
coverage, implementation and evidence assurance.  A positive questionnaire
coverage result is never represented as a legal-compliance conclusion.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Authority(str, Enum):
    BINDING = "binding"
    ENFORCEABLE_GUIDANCE = "enforceable_guidance"
    GUIDANCE = "guidance"
    VOLUNTARY = "voluntary"
    ENTERPRISE = "enterprise"


class ApplicabilityStatus(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    CONDITIONAL = "conditional"
    UNDETERMINED = "undetermined"


class CoverageStatus(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_ASSESSED = "not_assessed"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class GapType(str, Enum):
    QUESTIONNAIRE = "questionnaire_gap"
    ENTERPRISE_POLICY = "enterprise_policy_gap"
    CONTROL_CONFLICT = "control_conflict"
    IMPLEMENTATION_EVIDENCE = "implementation_evidence_gap"


class SourceRecord(BaseModel):
    source_id: str
    title: str
    authority: Authority
    jurisdiction: str
    version: str
    source_url: str
    effective_from: Optional[date] = None
    notes: Optional[str] = None


class AtomicObligation(BaseModel):
    obligation_id: str
    source_id: str
    instrument: str
    provision: str
    title: str
    jurisdiction: str = "AU"
    layer: str
    authority: Authority
    version: str
    source_url: str
    effective_from: Optional[date] = None
    applicability_key: str
    assessment_scope: Literal["use_case", "entity", "organisation"] = "use_case"
    control_id: str
    control_objective: str
    coverage_facets: List[str] = Field(min_length=1)
    evidence_requirements: List[str] = Field(default_factory=list)
    facet_keywords: Dict[str, List[str]] = Field(default_factory=dict)
    suggested_questions: Dict[str, str] = Field(default_factory=dict)
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    legal_note: Optional[str] = None

    @field_validator("coverage_facets")
    @classmethod
    def unique_facets(cls, facets: List[str]) -> List[str]:
        if len(facets) != len(set(facets)):
            raise ValueError("coverage_facets must be unique")
        return facets


class RegulatoryPack(BaseModel):
    pack_id: str
    version: str
    title: str
    verified_as_of: date
    disclaimer: str
    sources: List[SourceRecord]
    obligations: List[AtomicObligation]


class QuestionRecord(BaseModel):
    question_id: str
    question_text: str
    risk_domain: Optional[str] = None
    risk_factor_ids: List[str] = Field(default_factory=list)
    treatment_ids: List[str] = Field(default_factory=list)
    response_tags: List[str] = Field(default_factory=list)
    phase_tags: List[str] = Field(default_factory=list)
    sme_tags: List[str] = Field(default_factory=list)
    answer_options: List[str] = Field(default_factory=list)
    source_version: str
    source_sheet: str
    question_type: Literal["core", "benefit", "focus", "overlay"] = "focus"
    source_location: Optional[str] = None
    routing_logic: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    mapping_status: ReviewStatus = ReviewStatus.UNREVIEWED
    is_overlay: bool = False


class QuestionnaireMetadata(BaseModel):
    questionnaire_id: str
    source_filename: str
    source_sha256: str
    source_version: str
    header_fingerprint: str = ""
    imported_at: datetime = Field(default_factory=utc_now)
    sheets: Dict[str, str] = Field(default_factory=dict)
    core_question_count: int = 0
    benefit_question_count: int = 0
    focus_question_count: int = 0
    trigger_count: int = 0
    treatment_count: int = 0
    risk_count: int = 0
    warnings: List[str] = Field(default_factory=list)


class QuestionBank(BaseModel):
    metadata: QuestionnaireMetadata
    questions: List[QuestionRecord]
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
    routing_metadata: Dict[str, Any] = Field(default_factory=dict)


class QuestionRoutingSnapshot(BaseModel):
    snapshot_id: str
    tenant_id: str
    questionnaire_id: str
    questionnaire_sha256: str
    response_tags: List[str] = Field(default_factory=list)
    phase_tags: List[str] = Field(default_factory=list)
    selected_question_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class BankingUseCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    use_case_id: Optional[str] = None
    name: str = "Dispute and Refund Agent"
    entity_type: str = "UNDETERMINED"
    apra_regulated: Optional[bool] = None
    handles_personal_information: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices(
            "handles_personal_information", "processes_personal_information"
        ),
    )
    handles_sensitive_information: Optional[bool] = None
    makes_or_assists_significant_decisions: Optional[bool] = None
    handles_regulated_complaints: Optional[bool] = None
    idr_obligations: Optional[bool] = Field(
        default=None, validation_alias=AliasChoices("idr_obligations", "idr_obligation")
    )
    third_party_ai_service: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("third_party_ai_service", "uses_third_party_ai"),
    )
    supports_critical_operation: Optional[bool] = None
    material_service_provider: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices(
            "material_service_provider", "third_party_materiality"
        ),
    )
    eu_establishment_or_market: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices(
            "eu_establishment_or_market", "eu_territorial_nexus"
        ),
    )
    eu_output_used: Optional[bool] = None
    eu_deployer_or_provider_role: Optional[bool] = None
    nist_ai_rmf_adopted: Optional[bool] = None
    iso_42001_adopted: Optional[bool] = None
    assessment_scope: Literal["use_case", "entity", "organisation"] = "use_case"
    approval_threshold_aud: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    as_of_date: date = Field(default_factory=date.today)

    @model_validator(mode="before")
    @classmethod
    def selected_standards_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalised = dict(data)
        materiality = normalised.get("third_party_materiality")
        if isinstance(materiality, str):
            materiality_map = {
                "material": True,
                "non_material": False,
                "unknown": None,
            }
            if materiality.lower() in materiality_map:
                normalised["material_service_provider"] = materiality_map[
                    materiality.lower()
                ]
                normalised.pop("third_party_materiality", None)
        standards = {
            str(item).lower() for item in normalised.pop("selected_standards", [])
        }
        if standards:
            normalised.setdefault(
                "nist_ai_rmf_adopted", any("nist" in item for item in standards)
            )
            normalised.setdefault(
                "iso_42001_adopted",
                any("42001" in item or "iso" in item for item in standards),
            )
        return normalised


class ApplicabilityDecision(BaseModel):
    obligation_id: str
    status: ApplicabilityStatus
    reason: str
    authority: Authority
    assessment_scope: str
    rule_key: str


class MappingDecision(BaseModel):
    obligation_id: str
    facet: str
    question_id: str
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    source_reference: Optional[str] = None
    reviewer: Optional[str] = None
    reviewer_role: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    questionnaire_id: Optional[str] = None
    questionnaire_sha256: Optional[str] = None
    regulatory_pack_id: Optional[str] = None
    regulatory_pack_version: Optional[str] = None
    control_id: Optional[str] = None


class ObligationCoverage(BaseModel):
    obligation_id: str
    instrument: str
    provision: str
    title: str
    authority: Authority
    source_url: str
    applicability: ApplicabilityDecision
    confirmed_status: CoverageStatus
    provisional_status: CoverageStatus
    confirmed_question_ids: List[str] = Field(default_factory=list)
    candidate_question_ids: List[str] = Field(default_factory=list)
    confirmed_missing_facets: List[str] = Field(default_factory=list)
    provisional_missing_facets: List[str] = Field(default_factory=list)
    mappings: List[MappingDecision] = Field(default_factory=list)
    suggested_questions: List[str] = Field(default_factory=list)
    evidence_requirements: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "Coverage assesses whether the questionnaire asks about the requirement; "
        "it does not establish implementation, evidence effectiveness or legal compliance."
    )


class CoverageMetrics(BaseModel):
    applicable_binding_obligations: int = 0
    confirmed_covered: int = 0
    confirmed_partial: int = 0
    confirmed_missing: int = 0
    provisional_covered: int = 0
    provisional_partial: int = 0
    provisional_missing: int = 0
    applicability_conditional: int = 0
    applicability_undetermined: int = 0
    confirmed_coverage_rate: float = 0.0
    provisional_coverage_rate: float = 0.0


class CoverageAssessment(BaseModel):
    assessment_id: str
    tenant_id: str
    created_at: datetime = Field(default_factory=utc_now)
    questionnaire_id: str
    questionnaire_sha256: str
    regulatory_pack_id: str
    regulatory_pack_version: str
    routing_snapshot_id: Optional[str] = None
    selected_question_ids: List[str] = Field(default_factory=list)
    use_case: BankingUseCase
    metrics: CoverageMetrics
    results: List[ObligationCoverage]
    gaps: List["GapRecord"] = Field(default_factory=list)
    question_scope: Literal["core_only", "routed_snapshot"] = "core_only"
    selected_question_count: int = 0
    selection_warning: Optional[str] = None
    methodology: str = (
        "Deterministic applicability plus facet-level semantic candidates. "
        "Only approved mappings count as confirmed coverage."
    )


class PolicyClause(BaseModel):
    clause_id: str
    source_name: str
    text: str
    mandatory: bool
    control_facets: List[str] = Field(default_factory=list)
    thresholds_aud: List[float] = Field(default_factory=list)
    page: Optional[int] = None


class PolicyPack(BaseModel):
    policy_pack_id: str
    tenant_id: str
    name: str
    version: str = "unversioned"
    clauses: List[PolicyClause]
    warnings: List[str] = Field(default_factory=list)
    imported_at: datetime = Field(default_factory=utc_now)


class GapRecord(BaseModel):
    gap_id: str
    gap_type: GapType
    title: str
    status: Literal["open", "in_review", "closed", "rejected"] = "open"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    obligation_id: Optional[str] = None
    policy_clause_id: Optional[str] = None
    missing_facets: List[str] = Field(default_factory=list)
    recommendation: str
    evidence_required: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewer_role: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    closure_validated: bool = False
    closure_scope_rechecked: bool = False
    closure_approved: bool = False
    closure_evidence_artifact_ids: List[str] = Field(default_factory=list)
    closure_retest_record_id: Optional[str] = None


class PolicyGapAssessment(BaseModel):
    assessment_id: str
    tenant_id: str
    policy_pack_id: str
    questionnaire_id: str
    questionnaire_sha256: str
    regulatory_pack_id: str
    regulatory_pack_version: str
    routing_snapshot_id: Optional[str] = None
    selected_question_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    policy_gaps: List[GapRecord] = Field(default_factory=list)
    questionnaire_gaps: List[GapRecord] = Field(default_factory=list)
    control_conflicts: List[GapRecord] = Field(default_factory=list)
    implementation_evidence_gaps: List[GapRecord] = Field(default_factory=list)
    policy_clauses: List[PolicyClause] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @computed_field
    @property
    def gaps(self) -> List[GapRecord]:
        return [
            *self.policy_gaps,
            *self.questionnaire_gaps,
            *self.control_conflicts,
            *self.implementation_evidence_gaps,
        ]
