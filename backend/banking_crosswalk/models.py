"""Typed domain model for the Banking Regulatory Crosswalk.

These models deliberately separate legal applicability, questionnaire
coverage, implementation and evidence assurance.  A positive questionnaire
coverage result is never represented as a legal-compliance conclusion.
"""

from __future__ import annotations

import uuid

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


class LegalAuthorityClassification(str, Enum):
    BINDING_LEGAL_OR_PRUDENTIAL = "binding_legal_or_prudential_obligation"
    ENFORCEABLE_REGULATORY = "enforceable_regulatory_requirement"
    REGULATORY_GUIDANCE = "regulatory_guidance_and_expectation"
    VOLUNTARY_FRAMEWORK = "voluntary_framework"
    ENTERPRISE_CONTROL = "enterprise_defined_control"


class MappingRelationship(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    RELATED = "related"
    NON_EQUIVALENT = "non_equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    MISSING = "missing"
    UNDETERMINED = "undetermined"


AUTHORITY_TO_LEGAL_CLASSIFICATION: Dict[Authority, LegalAuthorityClassification] = {
    Authority.BINDING: LegalAuthorityClassification.BINDING_LEGAL_OR_PRUDENTIAL,
    Authority.ENFORCEABLE_GUIDANCE: LegalAuthorityClassification.ENFORCEABLE_REGULATORY,
    Authority.GUIDANCE: LegalAuthorityClassification.REGULATORY_GUIDANCE,
    Authority.VOLUNTARY: LegalAuthorityClassification.VOLUNTARY_FRAMEWORK,
    Authority.ENTERPRISE: LegalAuthorityClassification.ENTERPRISE_CONTROL,
}


def authority_layer_bucket(authority: Authority) -> str:
    if authority in {Authority.BINDING, Authority.ENFORCEABLE_GUIDANCE}:
        return "binding_regulatory"
    if authority is Authority.GUIDANCE:
        return "regulatory_guidance"
    if authority is Authority.VOLUNTARY:
        return "voluntary_frameworks"
    return "enterprise_internal_controls"


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
    regulator_or_publisher: str = "UNKNOWN"
    instrument_title: Optional[str] = None
    legal_authority_type: Optional[LegalAuthorityClassification] = None
    version_id: Optional[str] = None
    publication_date: Optional[str] = "UNKNOWN"
    effective_to: str = "NONE_CURRENT"
    verified_as_of: Optional[date] = None
    applicable_entity_types: List[str] = Field(default_factory=list)
    licence_conditions: str = "NONE_SPECIFIED"
    source_sha256: str = "NOT_DOWNLOADED_URL_REFERENCED"
    source_location: str = "OFFICIAL_EXTERNAL_URL"
    licensing_or_copyright_status: str = "UNKNOWN"
    extraction_status: str = "extracted_candidate_provisions"
    reviewer_status: ReviewStatus = ReviewStatus.PROPOSED
    temporal_status: Literal["current", "superseded", "future"] = "current"
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    historical_versions: List[Dict[str, Any]] = Field(default_factory=list)


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
    exact_clause_reference: Optional[str] = None
    concise_obligation_summary: Optional[str] = None
    legal_authority_classification: Optional[LegalAuthorityClassification] = None
    applicability_conditions: List[str] = Field(default_factory=list)
    entity_and_business_scope: Optional[str] = None
    effective_to: Optional[str] = "NONE_CURRENT"
    source_citation: Optional[str] = None
    source_location: Optional[str] = None
    extraction_confidence: Literal["high", "medium", "low"] = "high"
    extraction_uncertainty: Optional[str] = None
    reviewer_status: ReviewStatus = ReviewStatus.PROPOSED
    temporal_status: Literal["current", "superseded", "future"] = "current"
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None

    @field_validator("coverage_facets")
    @classmethod
    def unique_facets(cls, facets: List[str]) -> List[str]:
        if len(facets) != len(set(facets)):
            raise ValueError("coverage_facets must be unique")
        return facets


class UnifiedControl(BaseModel):
    control_id: str
    domain: str
    title: str
    control_objective: str
    assessment_scope: Literal["use_case", "entity", "organisation"] = "use_case"
    control_facets: List[str] = Field(min_length=1)
    associated_obligation_ids: List[str] = Field(default_factory=list)
    associated_source_ids: List[str] = Field(default_factory=list)
    evidence_requirements: List[str] = Field(default_factory=list)
    testing_and_assurance_guidance: Optional[str] = None
    copyright_and_provenance_note: Optional[str] = None
    review_status: ReviewStatus = ReviewStatus.PROPOSED

    @field_validator("control_facets")
    @classmethod
    def unique_control_facets(cls, facets: List[str]) -> List[str]:
        if len(facets) != len(set(facets)):
            raise ValueError("control_facets must be unique")
        return facets


class UnifiedControlLibrary(BaseModel):
    library_id: str
    version: str
    title: str
    verified_as_of: date
    domains: List[str]
    controls: List[UnifiedControl]


class ObligationControlMapping(BaseModel):
    mapping_id: str
    obligation_id: str
    source_id: str
    provision: str
    authority: Authority
    control_id: str
    control_domain: str
    mapping_relationship: MappingRelationship
    mapped_facets: List[str] = Field(default_factory=list)
    unmapped_obligation_facets: List[str] = Field(default_factory=list)
    equivalence_rationale: str
    mapping_uncertainty: Optional[str] = None
    requires_human_validation: bool = True
    review_status: ReviewStatus = ReviewStatus.PROPOSED
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class ObligationControlMappingCatalogue(BaseModel):
    catalogue_id: str
    version: str
    verified_as_of: date
    disclaimer: str
    mappings: List[ObligationControlMapping]


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
    question_type: Literal["core", "benefit", "focus", "overlay", "question", "general"] = "question"
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
    cross_border_disclosure: Optional[bool] = None
    makes_or_assists_significant_decisions: Optional[bool] = None
    handles_regulated_complaints: Optional[bool] = None
    idr_obligations: Optional[bool] = Field(
        default=None, validation_alias=AliasChoices("idr_obligations", "idr_obligation")
    )
    afs_licensee: Optional[bool] = None
    credit_licensee_or_credit_activity: Optional[bool] = None
    assists_consumer_credit_decision: Optional[bool] = None
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
    eu_operator_role: Optional[
        Literal["provider", "deployer", "importer", "distributor", "none"]
    ] = None
    nist_ai_rmf_adopted: Optional[bool] = None
    au_ai_guidance_adopted: Optional[bool] = None
    iso_42001_adopted: Optional[bool] = None
    iso_23894_adopted: Optional[bool] = None
    iso_27001_adopted: Optional[bool] = None
    enterprise_controls_enabled: Optional[bool] = None
    assessment_scope: Literal["use_case", "entity", "organisation"] = "use_case"
    approval_threshold_aud: Optional[float] = Field(
        default=None, ge=0, allow_inf_nan=False
    )
    approval_threshold_operator: Optional[Literal[">", ">=", "<", "<="]] = None
    approval_threshold_currency: Optional[str] = "AUD"
    approval_timing: Optional[Literal["pre_execution", "post_execution"]] = None
    approval_role: Optional[str] = None
    has_approved_exception: Optional[bool] = None
    exception_reference: Optional[str] = None
    as_of_date: date = Field(default_factory=date.today)

    @classmethod
    def enterprise_baseline(cls, **overrides: Any) -> "BankingUseCase":
        """Enterprise-level baseline for an Australian bank (ADI/AFSL/ACL).

        Allows comparing enterprise policies or questionnaires without requiring
        a complete AI use-case intake, while keeping EU AI Act out of scope by
        default unless a territorial nexus is explicitly specified.
        """
        defaults: Dict[str, Any] = {
            "name": "Australian Banking Enterprise Baseline",
            "entity_type": "ADI",
            "assessment_scope": "organisation",
            "apra_regulated": True,
            "handles_personal_information": True,
            "handles_sensitive_information": False,
            "cross_border_disclosure": False,
            "makes_or_assists_significant_decisions": True,
            "handles_regulated_complaints": True,
            "idr_obligations": True,
            "afs_licensee": True,
            "credit_licensee_or_credit_activity": True,
            "assists_consumer_credit_decision": True,
            "third_party_ai_service": True,
            "supports_critical_operation": True,
            "material_service_provider": True,
            "eu_establishment_or_market": False,
            "eu_output_used": False,
            "eu_deployer_or_provider_role": False,
            "nist_ai_rmf_adopted": True,
            "au_ai_guidance_adopted": True,
            "iso_42001_adopted": True,
            "iso_23894_adopted": True,
            "iso_27001_adopted": True,
            "enterprise_controls_enabled": True,
        }
        defaults.update(overrides)
        return cls(**defaults)

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
            if any("23894" in item for item in standards):
                normalised.setdefault("iso_23894_adopted", True)
            if any("27001" in item for item in standards):
                normalised.setdefault("iso_27001_adopted", True)
            if any("ai6" in item or "guidance" in item or "naic" in item for item in standards):
                normalised.setdefault("au_ai_guidance_adopted", True)
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


class LayerCoverageMetrics(BaseModel):
    layer_key: str
    applicable_obligations: int = 0
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
    by_authority_layer: Dict[str, LayerCoverageMetrics] = Field(default_factory=dict)


class CoverageAssessment(BaseModel):
    assessment_id: str
    tenant_id: str
    created_at: datetime = Field(default_factory=utc_now)
    assessment_mode: Literal["regulatory_only", "enterprise_enhanced", "provisional"] = "regulatory_only"
    assessment_target_type: Literal["questionnaire", "strategy", "use_case"] = "questionnaire"
    questionnaire_id: str
    questionnaire_sha256: str
    regulatory_pack_id: str
    regulatory_pack_version: str
    unified_control_library_version: Optional[str] = "2026.1"
    routing_snapshot_id: Optional[str] = None
    selected_question_ids: List[str] = Field(default_factory=list)
    use_case: BankingUseCase
    metrics: CoverageMetrics
    results: List[ObligationCoverage]
    gaps: List["GapRecord"] = Field(default_factory=list)
    enterprise_baseline_id: Optional[str] = None
    enterprise_baseline_version: Optional[str] = None
    enterprise_baseline_revision: Optional[int] = None
    enterprise_gaps: List["GapRecord"] = Field(default_factory=list)
    applicable_obligation_ids: List[str] = Field(default_factory=list)
    applicable_enterprise_requirement_ids: List[str] = Field(default_factory=list)
    question_scope: Literal["core_only", "routed_snapshot", "full_questionnaire"] = "full_questionnaire"
    selected_question_count: int = 0
    selection_warning: Optional[str] = None
    methodology: str = (
        "Deterministic applicability plus facet-level semantic candidates. "
        "Only approved mappings count as confirmed coverage."
    )
    legal_disclaimer: str = (
        "Assessment gaps do not constitute judicial or regulatory findings of legal non-compliance."
    )
    provenance: Optional[Dict[str, Any]] = None


class PolicyClause(BaseModel):
    clause_id: str
    source_name: str
    text: str
    mandatory: bool
    control_facets: List[str] = Field(default_factory=list)
    thresholds_aud: List[float] = Field(default_factory=list)
    page: Optional[int] = None
    threshold_operator: Optional[Literal[">", ">=", "<", "<="]] = None
    threshold_currency: Optional[str] = None
    approval_timing: Optional[Literal["pre_execution", "post_execution"]] = None
    required_approval_role: Optional[str] = None
    is_conditional: bool = False
    has_exception_clause: bool = False
    implementation_status: Optional[str] = None




class EnterpriseAuthorityLevel(str, Enum):
    STATUTORY = "statutory"
    REGULATORY_GUIDANCE = "regulatory_guidance"
    INDUSTRY_FRAMEWORK = "industry_framework"
    ENTERPRISE_POLICY = "enterprise_policy"
    CONTRACTUAL = "contractual"
    AUDIT_FINDING = "audit_finding"


class ClauseReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClauseControlMapping(BaseModel):
    mapping_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    clause_id: str
    control_id: str
    relationship: MappingRelationship = MappingRelationship.FULL
    rationale: Optional[str] = None
    review_status: ClauseReviewStatus = ClauseReviewStatus.PROPOSED
    created_at: datetime = Field(default_factory=utc_now)


class EnterpriseClause(BaseModel):
    clause_id: str
    policy_id: str
    tenant_id: str
    source_name: str
    clause_number: Optional[str] = None
    text: str
    mandatory: bool = True
    authority_level: EnterpriseAuthorityLevel = EnterpriseAuthorityLevel.ENTERPRISE_POLICY
    control_facets: List[str] = Field(default_factory=list)
    thresholds_aud: List[float] = Field(default_factory=list)
    page: Optional[int] = None
    is_unmapped: bool = False
    review_status: ClauseReviewStatus = ClauseReviewStatus.PROPOSED
    reviewer_actor: Optional[str] = None
    reviewer_role: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    control_mappings: List[ClauseControlMapping] = Field(default_factory=list)
    threshold_operator: Optional[Literal[">", ">=", "<", "<="]] = None
    threshold_currency: Optional[str] = None
    approval_timing: Optional[Literal["pre_execution", "post_execution"]] = None
    required_approval_role: Optional[str] = None
    is_conditional: bool = False
    condition_description: Optional[str] = None
    has_exception_clause: bool = False
    exception_description: Optional[str] = None
    implementation_status: Optional[Literal["implemented", "unimplemented", "unverified"]] = None


class EnterprisePolicy(BaseModel):
    policy_id: str
    tenant_id: str
    name: str
    category: str = "general"
    authority_level: EnterpriseAuthorityLevel = EnterpriseAuthorityLevel.ENTERPRISE_POLICY
    version: str = "1.0.0"
    status: Literal["active", "draft", "superseded", "retired"] = "active"
    effective_date: Optional[datetime] = None
    file_sha256: str = ""
    clauses: List[EnterpriseClause] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: Optional[str] = None


class EnterpriseBaseline(BaseModel):
    baseline_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    version: str = "1.0.0"
    revision: int = 1
    policy_ids: List[str] = Field(default_factory=list)
    confirmed_control_ids: List[str] = Field(default_factory=list)
    pending_clause_ids: List[str] = Field(default_factory=list)
    unmapped_clause_ids: List[str] = Field(default_factory=list)
    conflicts: List[GapRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    baseline_sha256: Optional[str] = None
    status: Literal["active", "archived", "draft"] = "active"
    clause_snapshots: List["EnterpriseClause"] = Field(default_factory=list)
    source_policy_versions: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    created_by: Optional[str] = None


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
    revision: int = Field(default=1, ge=1)
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
    source_type: Optional[Literal["regulatory", "enterprise_policy", "internal_conflict"]] = None
    closure_retest_record_id: Optional[str] = None
    required_threshold: Optional[float] = None
    use_case_threshold: Optional[float] = None
    threshold_operator: Optional[str] = None
    use_case_operator: Optional[str] = None
    timing_required: Optional[str] = None
    use_case_timing: Optional[str] = None
    role_required: Optional[str] = None
    use_case_role: Optional[str] = None
    evidence_missing: Optional[bool] = None


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
    gaps_by_authority_layer: Dict[str, List[GapRecord]] = Field(default_factory=dict)
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


EnterpriseBaseline.model_rebuild()
CoverageAssessment.model_rebuild()
GapRecord.model_rebuild()
