"""Phase 8 automated technical validation and synthetic evaluation suite.

Clearly differentiates deterministic technical/schema validation from expert
Australian financial-services legal and regulatory sign-off.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional

from .applicability import RULES, decide_applicability
from .catalog import (
    load_aiaf_question_bank,
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_source_register,
    load_unified_control_library,
)
from .coverage import evaluate_questionnaire_coverage
from .models import (
    AUTHORITY_TO_LEGAL_CLASSIFICATION,
    ApplicabilityStatus,
    Authority,
    BankingUseCase,
    LegalAuthorityClassification,
    MappingRelationship,
    ObligationControlMappingCatalogue,
    QuestionBank,
    QuestionRecord,
    QuestionnaireMetadata,
    RegulatoryPack,
    ReviewStatus,
    SourceRecord,
    UnifiedControlLibrary,
)
from .policy import assess_policy_gaps, extract_policy_pack


PROVISION_TOKEN_RE = re.compile(
    r"(APP\s*\d+|s\s*\d+|ss\s*\d+|para|paragraph|Clause|Annex|Article|Art\.|Chapter|Ch\s*\d+|Part|Schedule|RG\s*\d+|CPS\s*\d+|CPG\s*\d+|REP\s*\d+|GOVERN|MAP|MEASURE|MANAGE|Practice\s*\d+|E-DA-\d+)",
    re.IGNORECASE,
)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ALLOWED_PHASED_CHILD_DATES = {
    "AU-PRIV-APP1-GOV",
    "AU-PRIV-APP3-COLLECT",
    "AU-PRIV-APP5-NOTICE",
    "AU-PRIV-APP6-USE",
    "AU-PRIV-APP8-CROSSBORDER",
    "AU-PRIV-APP10-QUALITY",
    "AU-PRIV-APP11-SECURITY",
    "AU-PRIV-APP12-13-RIGHTS",
    "AU-PRIV-NDB-S26WE",
    "AU-PRIV-APP1.7-AUTOMATED",
    "AU-OAIC-APPG-CH1-PIA",
    "AU-OAIC-APPG-CH6-CH10-INF",
    "AU-ASIC-RG104-COMPLIANCE",
    "AU-ASIC-RG105-COMPETENCE",
    "EU-AIA-ART2-HIGH-RISK",
    "EU-AIA-ART4-5-PROHIBITED-LITERACY",
    "EU-AIA-ART26-27-DEPLOYER-CREDIT",
}


def _parse_iso_date(val: Any) -> Optional[date]:
    if isinstance(val, date):
        return val
    if not val or str(val) in {"NONE_CURRENT", "UNKNOWN", "N/A"}:
        return None
    s = str(val).strip()
    if not ISO_DATE_RE.match(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def validate_regulatory_library(
    pack: Optional[RegulatoryPack] = None,
    source_register: Optional[List[SourceRecord]] = None,
    control_library: Optional[UnifiedControlLibrary] = None,
    mapping_catalogue: Optional[ObligationControlMappingCatalogue] = None,
    forbid_auto_approved: bool = True,
) -> Dict[str, Any]:
    """Run all 9 automated technical validation checks over the regulatory library."""
    active_pack = pack or load_regulatory_pack()
    active_register = (
        source_register if source_register is not None else load_source_register()
    )
    active_controls = control_library or load_unified_control_library()
    active_mappings = mapping_catalogue or load_obligation_control_mappings()

    pack_sources = {s.source_id: s for s in active_pack.sources}
    register_sources = {s.source_id: s for s in active_register}
    obligations = active_pack.obligations
    controls_by_id = {c.control_id: c for c in active_controls.controls}

    # 1. Missing source references
    missing_source_errors: List[str] = []
    for ob in obligations:
        if ob.source_id not in pack_sources:
            missing_source_errors.append(
                f"Obligation {ob.obligation_id} references source_id '{ob.source_id}' missing from pack.sources"
            )
        if ob.source_id not in register_sources:
            missing_source_errors.append(
                f"Obligation {ob.obligation_id} references source_id '{ob.source_id}' missing from source register CSV"
            )
    for m in active_mappings.mappings:
        if m.source_id not in pack_sources:
            missing_source_errors.append(
                f"Mapping {m.mapping_id} references unknown source_id '{m.source_id}'"
            )
    for s_id in pack_sources:
        if s_id not in register_sources:
            missing_source_errors.append(
                f"Pack source '{s_id}' is missing from REGULATORY_SOURCE_REGISTER.csv"
            )

    # 2. Invalid provision references
    invalid_provision_errors: List[str] = []
    for ob in obligations:
        if not ob.provision or not ob.provision.strip():
            invalid_provision_errors.append(
                f"Obligation {ob.obligation_id} has an empty provision"
            )
        elif not PROVISION_TOKEN_RE.search(ob.provision):
            invalid_provision_errors.append(
                f"Obligation {ob.obligation_id} provision '{ob.provision}' lacks a recognised statutory/standard clause token"
            )
        if not ob.exact_clause_reference or not ob.exact_clause_reference.strip():
            invalid_provision_errors.append(
                f"Obligation {ob.obligation_id} is missing exact_clause_reference"
            )
        if not ob.source_citation or not ob.source_citation.strip():
            invalid_provision_errors.append(
                f"Obligation {ob.obligation_id} is missing source_citation"
            )
        if not ob.source_url.startswith("https://"):
            invalid_provision_errors.append(
                f"Obligation {ob.obligation_id} has invalid non-HTTPS source_url '{ob.source_url}'"
            )

    # 3. Duplicate obligations
    duplicate_obligation_errors: List[str] = []
    seen_ids: set[str] = set()
    seen_clause_keys: set[tuple[str, str, str]] = set()
    for ob in obligations:
        if ob.obligation_id in seen_ids:
            duplicate_obligation_errors.append(
                f"Duplicate obligation_id '{ob.obligation_id}'"
            )
        seen_ids.add(ob.obligation_id)
        clause_key = (
            ob.source_id.strip().upper(),
            (ob.exact_clause_reference or ob.provision).strip().lower(),
            ob.title.strip().lower(),
        )
        if clause_key in seen_clause_keys:
            duplicate_obligation_errors.append(
                f"Duplicate obligation clause+title combination for {ob.obligation_id}: {clause_key}"
            )
        seen_clause_keys.add(clause_key)

    # 4. Unmapped control facets
    unmapped_facet_errors: List[str] = []
    ob_by_id = {ob.obligation_id: ob for ob in obligations}
    primary_mappings_by_ob: Dict[str, List[Any]] = {}
    for m in active_mappings.mappings:
        if m.obligation_id not in ob_by_id:
            unmapped_facet_errors.append(
                f"Mapping {m.mapping_id} references unknown obligation_id '{m.obligation_id}'"
            )
            continue
        if m.control_id not in controls_by_id:
            unmapped_facet_errors.append(
                f"Mapping {m.mapping_id} references unknown control_id '{m.control_id}'"
            )
            continue
        target_ob = ob_by_id[m.obligation_id]
        ob_facet_set = set(target_ob.coverage_facets)
        mapped_union = set(m.mapped_facets) | set(m.unmapped_obligation_facets)
        unknown_facets = mapped_union - ob_facet_set
        if unknown_facets:
            unmapped_facet_errors.append(
                f"Mapping {m.mapping_id} cites facets not on {m.obligation_id}: {sorted(unknown_facets)}"
            )
        if m.control_id == target_ob.control_id:
            primary_mappings_by_ob.setdefault(m.obligation_id, []).append(m)

    for ob in obligations:
        if ob.control_id not in controls_by_id:
            unmapped_facet_errors.append(
                f"Obligation {ob.obligation_id} references missing control_id '{ob.control_id}'"
            )
            continue
        ctrl = controls_by_id[ob.control_id]
        missing_in_ctrl = [
            f for f in ob.coverage_facets if f not in ctrl.control_facets
        ]
        if missing_in_ctrl:
            unmapped_facet_errors.append(
                f"Obligation {ob.obligation_id} has facets missing from UnifiedControl {ctrl.control_id}: {missing_in_ctrl}"
            )
        missing_kw = [f for f in ob.coverage_facets if f not in ob.facet_keywords]
        if missing_kw:
            unmapped_facet_errors.append(
                f"Obligation {ob.obligation_id} is missing facet_keywords for facets: {missing_kw}"
            )
        primary_ms = primary_mappings_by_ob.get(ob.obligation_id, [])
        if not primary_ms:
            unmapped_facet_errors.append(
                f"Obligation {ob.obligation_id} has no primary mapping to {ob.control_id} in OBLIGATION_CONTROL_MAPPINGS.json"
            )
        else:
            covered_in_primary = set()
            for pm in primary_ms:
                covered_in_primary.update(pm.mapped_facets)
            uncovered = [
                f for f in ob.coverage_facets if f not in covered_in_primary
            ]
            if uncovered:
                unmapped_facet_errors.append(
                    f"Obligation {ob.obligation_id} has facets not covered by its primary control mapping: {uncovered}"
                )

    # 5. Conflicting effective dates
    conflicting_date_errors: List[str] = []
    for src in active_pack.sources:
        eff_from = _parse_iso_date(src.effective_from)
        if src.effective_from and eff_from is None:
            conflicting_date_errors.append(
                f"Source {src.source_id} has invalid effective_from date '{src.effective_from}'"
            )
        eff_to = _parse_iso_date(src.effective_to)
        if (
            src.effective_to
            and src.effective_to not in {"NONE_CURRENT", "UNKNOWN", "N/A"}
            and eff_to is None
        ):
            conflicting_date_errors.append(
                f"Source {src.source_id} has invalid effective_to date '{src.effective_to}'"
            )
        if eff_from and eff_to and eff_to < eff_from:
            conflicting_date_errors.append(
                f"Source {src.source_id} has effective_to ({eff_to}) earlier than effective_from ({eff_from})"
            )

    for ob in obligations:
        ob_from = _parse_iso_date(ob.effective_from)
        if ob.effective_from and ob_from is None:
            conflicting_date_errors.append(
                f"Obligation {ob.obligation_id} has invalid effective_from '{ob.effective_from}'"
            )
        ob_to = _parse_iso_date(ob.effective_to)
        if (
            ob.effective_to
            and ob.effective_to not in {"NONE_CURRENT", "UNKNOWN", "N/A"}
            and ob_to is None
        ):
            conflicting_date_errors.append(
                f"Obligation {ob.obligation_id} has invalid effective_to '{ob.effective_to}'"
            )
        if ob_from and ob_to and ob_to < ob_from:
            conflicting_date_errors.append(
                f"Obligation {ob.obligation_id} has effective_to ({ob_to}) earlier than effective_from ({ob_from})"
            )
        parent_src = pack_sources.get(ob.source_id)
        if parent_src and ob_from:
            src_from = _parse_iso_date(parent_src.effective_from)
            if (
                src_from
                and ob_from != src_from
                and ob.obligation_id not in ALLOWED_PHASED_CHILD_DATES
            ):
                conflicting_date_errors.append(
                    f"Obligation {ob.obligation_id} effective_from ({ob_from}) conflicts with parent source {parent_src.source_id} effective_from ({src_from}) without phased-commencement registration"
                )

    # 6. Incorrect legal authority classification
    authority_errors: List[str] = []
    non_binding_sources = {
        "AU-OAIC-APP-GUIDELINES",
        "APRA-CPG235",
        "ASIC-REP798",
        "AU-AI-GUIDANCE-2025",
        "NIST-AI-RMF",
        "ISO-42001",
        "ISO-23894",
        "ISO-27001",
    }
    voluntary_only_sources = {
        "NIST-AI-RMF",
        "ISO-42001",
        "ISO-23894",
        "ISO-27001",
    }
    for ob in obligations:
        expected_cls = AUTHORITY_TO_LEGAL_CLASSIFICATION.get(ob.authority)
        if ob.legal_authority_classification != expected_cls:
            authority_errors.append(
                f"Obligation {ob.obligation_id} authority '{ob.authority.value}' mismatches legal_authority_classification '{ob.legal_authority_classification}'"
            )
        parent_src = pack_sources.get(ob.source_id)
        if parent_src and parent_src.authority != ob.authority:
            authority_errors.append(
                f"Obligation {ob.obligation_id} authority '{ob.authority.value}' conflicts with parent source {parent_src.source_id} authority '{parent_src.authority.value}'"
            )
        if ob.source_id in non_binding_sources and ob.authority in {
            Authority.BINDING,
            Authority.ENFORCEABLE_GUIDANCE,
        }:
            authority_errors.append(
                f"Non-binding source {ob.source_id} obligation {ob.obligation_id} is misclassified as binding/enforceable ({ob.authority.value})"
            )
        if ob.source_id in voluntary_only_sources and (
            ob.legal_authority_classification
            != LegalAuthorityClassification.VOLUNTARY_FRAMEWORK
        ):
            authority_errors.append(
                f"Voluntary framework {ob.source_id} obligation {ob.obligation_id} must be classified as voluntary_framework"
            )

    # 7. Unreviewed mappings and candidate obligations check
    unreviewed_errors: List[str] = []
    approved_obligations = [
        ob.obligation_id
        for ob in obligations
        if ob.review_status == ReviewStatus.APPROVED
    ]
    proposed_obligations = [
        ob.obligation_id
        for ob in obligations
        if ob.review_status == ReviewStatus.PROPOSED
    ]
    approved_mappings = [
        m.mapping_id
        for m in active_mappings.mappings
        if m.review_status == ReviewStatus.APPROVED
    ]
    proposed_mappings = [
        m.mapping_id
        for m in active_mappings.mappings
        if m.review_status == ReviewStatus.PROPOSED
    ]
    if forbid_auto_approved and approved_obligations:
        unreviewed_errors.append(
            f"Candidate obligations must not be auto-approved without human legal sign-off: {approved_obligations}"
        )
    if forbid_auto_approved and approved_mappings:
        unreviewed_errors.append(
            f"Proposed crosswalk mappings must not be auto-approved without human sign-off: {approved_mappings}"
        )
    for m in active_mappings.mappings:
        if not m.requires_human_validation and m.review_status == ReviewStatus.PROPOSED:
            unreviewed_errors.append(
                f"Mapping {m.mapping_id} is proposed but requires_human_validation is False"
            )

    # 8. Unsupported applicability decisions
    applicability_errors: List[str] = []
    enterprise_uc = BankingUseCase.enterprise_baseline(
        as_of_date=date(2026, 10, 27)
    )
    full_uc = BankingUseCase(
        name="Synthetic Full-Scope Banking AI Use Case",
        entity_type="ADI",
        apra_regulated=True,
        afs_licensee=True,
        credit_licensee_or_credit_activity=True,
        assists_consumer_credit_decision=True,
        handles_personal_information=True,
        handles_sensitive_information=True,
        cross_border_disclosure=True,
        makes_or_assists_significant_decisions=True,
        handles_regulated_complaints=True,
        idr_obligations=True,
        third_party_ai_service=True,
        supports_critical_operation=True,
        material_service_provider=True,
        eu_establishment_or_market=True,
        eu_output_used=True,
        eu_deployer_or_provider_role=True,
        eu_operator_role="deployer",
        nist_ai_rmf_adopted=True,
        au_ai_guidance_adopted=True,
        iso_42001_adopted=True,
        iso_23894_adopted=True,
        iso_27001_adopted=True,
        enterprise_controls_enabled=True,
        assessment_scope="organisation",
        approval_threshold_aud=500.0,
        as_of_date=date(2026, 10, 27),
    )
    valid_statuses = {
        ApplicabilityStatus.APPLICABLE,
        ApplicabilityStatus.CONDITIONAL,
        ApplicabilityStatus.NOT_APPLICABLE,
        ApplicabilityStatus.UNDETERMINED,
    }
    for ob in obligations:
        if ob.applicability_key not in RULES:
            applicability_errors.append(
                f"Obligation {ob.obligation_id} uses unsupported applicability_key '{ob.applicability_key}'"
            )
            continue
        for mode_name, uc in [
            ("enterprise_baseline", enterprise_uc),
            ("full_use_case", full_uc),
        ]:
            decision = decide_applicability(ob, uc)
            if decision.status not in valid_statuses:
                applicability_errors.append(
                    f"Obligation {ob.obligation_id} returned invalid status '{decision.status}' in {mode_name}"
                )
            if not decision.reason or not decision.reason.strip():
                applicability_errors.append(
                    f"Obligation {ob.obligation_id} returned empty applicability reason in {mode_name}"
                )

    # 9. Broken existing analysis behaviour
    analysis_errors: List[str] = []
    try:
        qbank = load_aiaf_question_bank()
        cov_enterprise = evaluate_questionnaire_coverage(
            tenant_id="tenant-val",
            use_case=None,
            question_bank=qbank,
            regulatory_pack=active_pack,
        )
        cov_use_case = evaluate_questionnaire_coverage(
            tenant_id="tenant-val",
            use_case=full_uc,
            question_bank=qbank,
            regulatory_pack=active_pack,
        )
        expected_layers = {
            "binding_regulatory",
            "regulatory_guidance",
            "voluntary_frameworks",
            "enterprise_internal_controls",
        }
        if set(cov_enterprise.metrics.by_authority_layer.keys()) != expected_layers:
            analysis_errors.append(
                "Coverage metrics missing expected authority layer separation keys"
            )
        if len(cov_use_case.results) != len(obligations):
            analysis_errors.append(
                f"Coverage assessment count ({len(cov_use_case.results)}) does not match obligation count ({len(obligations)})"
            )

        policy_pack = extract_policy_pack(
            tenant_id="tenant-val",
            name="Validation Enterprise Policy",
            text="All refunds above AUD $500 must have human approval before payment execution and retain an audit log.",
        )
        gap_enterprise = assess_policy_gaps(
            tenant_id="tenant-val",
            use_case=None,
            policy_pack=policy_pack,
            question_bank=qbank,
            regulatory_pack=active_pack,
        )
        if not gap_enterprise.policy_gaps:
            analysis_errors.append(
                "Enterprise policy gap engine failed to detect expected findings"
            )
        if set(gap_enterprise.gaps_by_authority_layer.keys()) != expected_layers:
            analysis_errors.append(
                "Policy gap assessment missing expected authority layer separation keys"
            )
    except Exception as exc:  # pragma: no cover - defensive diagnostic
        analysis_errors.append(f"Existing analysis engine raised exception: {exc}")

    checks = {
        "missing_source_references": {
            "passed": len(missing_source_errors) == 0,
            "error_count": len(missing_source_errors),
            "errors": missing_source_errors,
        },
        "invalid_provision_references": {
            "passed": len(invalid_provision_errors) == 0,
            "error_count": len(invalid_provision_errors),
            "errors": invalid_provision_errors,
        },
        "duplicate_obligations": {
            "passed": len(duplicate_obligation_errors) == 0,
            "error_count": len(duplicate_obligation_errors),
            "errors": duplicate_obligation_errors,
        },
        "unmapped_control_facets": {
            "passed": len(unmapped_facet_errors) == 0,
            "error_count": len(unmapped_facet_errors),
            "errors": unmapped_facet_errors,
        },
        "conflicting_effective_dates": {
            "passed": len(conflicting_date_errors) == 0,
            "error_count": len(conflicting_date_errors),
            "errors": conflicting_date_errors,
        },
        "incorrect_legal_authority_classification": {
            "passed": len(authority_errors) == 0,
            "error_count": len(authority_errors),
            "errors": authority_errors,
        },
        "unreviewed_mappings": {
            "passed": len(unreviewed_errors) == 0,
            "error_count": len(unreviewed_errors),
            "errors": unreviewed_errors,
            "proposed_obligations_awaiting_human_review": len(proposed_obligations),
            "approved_obligations_count": len(approved_obligations),
            "proposed_mappings_awaiting_human_review": len(proposed_mappings),
            "approved_mappings_count": len(approved_mappings),
        },
        "unsupported_applicability_decisions": {
            "passed": len(applicability_errors) == 0,
            "error_count": len(applicability_errors),
            "errors": applicability_errors,
        },
        "broken_existing_analysis_behaviour": {
            "passed": len(analysis_errors) == 0,
            "error_count": len(analysis_errors),
            "errors": analysis_errors,
        },
    }

    all_passed = all(c["passed"] for c in checks.values())
    return {
        "valid": all_passed,
        "technical_validation_passed": all_passed,
        "legal_review_status": "pending_expert_human_review",
        "differentiation_notice": (
            "Automated technical validation confirms schema integrity, citation formatting, "
            "facet completeness, applicability rule determinism and engine compatibility. "
            "It does NOT constitute legal advice or approve candidate obligations; all "
            f"{len(proposed_obligations)} obligations and {len(proposed_mappings)} crosswalk "
            "mappings remain in 'proposed' status awaiting qualified Australian financial-services "
            "legal and regulatory review."
        ),
        "summary": {
            "sources_count": len(active_pack.sources),
            "obligations_count": len(obligations),
            "proposed_obligations_count": len(proposed_obligations),
            "approved_obligations_count": len(approved_obligations),
            "unified_controls_count": len(active_controls.controls),
            "mappings_count": len(active_mappings.mappings),
            "proposed_mappings_count": len(proposed_mappings),
            "approved_mappings_count": len(approved_mappings),
        },
        "checks": checks,
    }


def run_synthetic_evaluation_suite(
    pack: Optional[RegulatoryPack] = None,
    mapping_catalogue: Optional[ObligationControlMappingCatalogue] = None,
) -> Dict[str, Any]:
    """Execute the 6 synthetic evaluation scenarios required by Phase 8."""
    active_pack = pack or load_regulatory_pack()
    active_mappings = mapping_catalogue or load_obligation_control_mappings()

    # Scenario 1: Questionnaire coverage examples (enterprise baseline vs use-case specific)
    synthetic_qbank = QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id="SYNTH-QBANK-01",
            source_filename="synthetic_eval.json",
            source_sha256="0" * 64,
            source_version="eval-1.0",
            core_question_count=3,
        ),
        questions=[
            QuestionRecord(
                question_id="SYNTH-Q1",
                question_text=(
                    "Has a privacy impact assessment (PIA) been completed and is personal "
                    "information collection necessary for the function, with collection notice "
                    "and opt-out or consent for sensitive information?"
                ),
                source_version="eval-1.0",
                source_sheet="Questions",
                question_type="core",
            ),
            QuestionRecord(
                question_id="SYNTH-Q2",
                question_text=(
                    "Are information security controls commensurate with vulnerabilities, "
                    "including adversarial prompt injection and red team security testing, "
                    "and is APRA notified within 72 hours of a material security incident?"
                ),
                source_version="eval-1.0",
                source_sheet="Questions",
                question_type="core",
            ),
            QuestionRecord(
                question_id="SYNTH-Q3",
                question_text=(
                    "Does the workflow require human approval from an authorised officer "
                    "above the AUD threshold, prevent execution before payment, and retain "
                    "approval audit logs for seven years?"
                ),
                source_version="eval-1.0",
                source_sheet="Questions",
                question_type="core",
            ),
        ],
    )
    cov_baseline = evaluate_questionnaire_coverage(
        tenant_id="tenant-eval",
        use_case=None,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )

    # Scenario 2: Enterprise policy gap examples
    partial_policy = extract_policy_pack(
        tenant_id="tenant-eval",
        name="Partial Enterprise AI Policy",
        text=(
            "1. All AI systems handling personal information must complete a Privacy Impact Assessment (PIA) and provide a collection notice.\n"
            "2. AI systems must not use customer data for external model training without consent.\n"
        ),
    )
    gap_eval = assess_policy_gaps(
        tenant_id="tenant-eval",
        use_case=None,
        policy_pack=partial_policy,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )
    gap_obligation_ids = {
        g.obligation_id for g in gap_eval.policy_gaps if g.obligation_id
    }

    # Scenario 3: Correct and incorrect (non-equivalent) control mappings
    rel_counts: Dict[str, int] = {
        rel.value: 0 for rel in MappingRelationship
    }
    non_equivalent_pairs: List[Dict[str, str]] = []
    for m in active_mappings.mappings:
        rel_counts[m.mapping_relationship.value] += 1
        if m.mapping_relationship == MappingRelationship.NON_EQUIVALENT:
            non_equivalent_pairs.append(
                {
                    "mapping_id": m.mapping_id,
                    "obligation_id": m.obligation_id,
                    "control_id": m.control_id,
                    "equivalence_rationale": m.equivalence_rationale,
                }
            )

    # Scenario 4: Inapplicable obligations
    internal_use_case = BankingUseCase(
        name="Internal Staff Policy Search Assistant (Non-Credit, Onshore, No PII)",
        entity_type="ADI",
        apra_regulated=True,
        afs_licensee=True,
        credit_licensee_or_credit_activity=False,
        assists_consumer_credit_decision=False,
        handles_personal_information=False,
        handles_sensitive_information=False,
        cross_border_disclosure=False,
        makes_or_assists_significant_decisions=False,
        handles_regulated_complaints=False,
        idr_obligations=False,
        third_party_ai_service=False,
        supports_critical_operation=False,
        material_service_provider=False,
        eu_establishment_or_market=False,
        eu_output_used=False,
        eu_deployer_or_provider_role=False,
        eu_operator_role="none",
        nist_ai_rmf_adopted=False,
        au_ai_guidance_adopted=False,
        iso_42001_adopted=False,
        iso_23894_adopted=False,
        iso_27001_adopted=False,
        enterprise_controls_enabled=False,
        as_of_date=date(2026, 10, 27),
    )
    inapplicable_cov = evaluate_questionnaire_coverage(
        tenant_id="tenant-eval",
        use_case=internal_use_case,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )
    inapplicable_by_id = {
        r.obligation_id: r.applicability.status for r in inapplicable_cov.results
    }

    # Scenario 5: Conditional obligations (future-dated APP 1.7-1.9 & conditional cross-border / EU nexus)
    conditional_use_case_pre = BankingUseCase(
        name="Automated Credit Scoring Engine (Evaluated Oct 2026 before APP 1.7 commencement)",
        entity_type="ADI",
        apra_regulated=True,
        handles_personal_information=True,
        third_party_ai_service=True,
        cross_border_disclosure=None,
        makes_or_assists_significant_decisions=True,
        supports_critical_operation=None,
        as_of_date=date(2026, 10, 27),
    )
    conditional_use_case_post = conditional_use_case_pre.model_copy(
        update={"as_of_date": date(2026, 12, 15)}
    )
    cov_pre = evaluate_questionnaire_coverage(
        tenant_id="tenant-eval",
        use_case=conditional_use_case_pre,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )
    cov_post = evaluate_questionnaire_coverage(
        tenant_id="tenant-eval",
        use_case=conditional_use_case_post,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )
    pre_status = {r.obligation_id: r.applicability.status for r in cov_pre.results}
    post_status = {r.obligation_id: r.applicability.status for r in cov_post.results}

    # Scenario 6: Conflicting policy and system thresholds
    threshold_policy = extract_policy_pack(
        tenant_id="tenant-eval",
        name="Enterprise Financial Delegated Authority Policy",
        text="1. Any AI-recommended refund above AUD $500 must require human approval from an authorised officer before payment execution and retain an approval audit log.",
    )
    conflicting_use_case = BankingUseCase.enterprise_baseline(
        approval_threshold_aud=2500.0
    )
    threshold_gap_eval = assess_policy_gaps(
        tenant_id="tenant-eval",
        use_case=conflicting_use_case,
        policy_pack=threshold_policy,
        question_bank=synthetic_qbank,
        regulatory_pack=active_pack,
    )

    scenarios = {
        "questionnaire_coverage_examples": {
            "passed": (
                len(cov_baseline.results) == len(active_pack.obligations)
                and cov_baseline.metrics.by_authority_layer["binding_regulatory"].applicable_obligations > 0
                and cov_baseline.metrics.by_authority_layer["regulatory_guidance"].applicable_obligations > 0
            ),
            "enterprise_baseline_metrics": cov_baseline.metrics.model_dump(mode="json"),
        },
        "enterprise_policy_gap_examples": {
            "passed": {
                "AU-APRA-CPS234-INCIDENT",
                "AU-APRA-CPS230-SP",
                "AU-ASIC-RG271-COMPLAINT",
                "AU-NCCP-S128-131-LENDING",
            }.issubset(gap_obligation_ids)
            and len(gap_eval.gaps_by_authority_layer["binding_regulatory"]) > 0
            and len(gap_eval.gaps_by_authority_layer["regulatory_guidance"]) > 0
            and len(gap_eval.gaps_by_authority_layer["voluntary_frameworks"]) >= 0
            and len(gap_eval.gaps_by_authority_layer["enterprise_internal_controls"]) == 0,
            "binding_gap_count": len(gap_eval.gaps_by_authority_layer["binding_regulatory"]),
            "guidance_gap_count": len(gap_eval.gaps_by_authority_layer["regulatory_guidance"]),
            "voluntary_gap_count": len(gap_eval.gaps_by_authority_layer["voluntary_frameworks"]),
            "enterprise_gap_count": len(gap_eval.gaps_by_authority_layer["enterprise_internal_controls"]),
        },
        "correct_and_incorrect_control_mappings": {
            "passed": (
                rel_counts["full"] > 0
                and rel_counts["partial"] > 0
                and rel_counts["related"] > 0
                and rel_counts["non_equivalent"] >= 3
            ),
            "relationship_counts": rel_counts,
            "non_equivalent_mappings": non_equivalent_pairs,
        },
        "inapplicable_obligations": {
            "passed": (
                inapplicable_by_id["EU-AIA-ART2-HIGH-RISK"] == ApplicabilityStatus.NOT_APPLICABLE
                and inapplicable_by_id["AU-NCCP-S128-131-LENDING"] == ApplicabilityStatus.NOT_APPLICABLE
                and inapplicable_by_id["AU-PRIV-APP8-CROSSBORDER"] == ApplicabilityStatus.NOT_APPLICABLE
                and inapplicable_by_id["AU-APRA-CPS230-SP"] == ApplicabilityStatus.NOT_APPLICABLE
                and inapplicable_by_id["AU-APRA-CPS220-RMF"] == ApplicabilityStatus.APPLICABLE
            ),
            "sample_statuses": {
                k: inapplicable_by_id[k].value
                for k in [
                    "EU-AIA-ART2-HIGH-RISK",
                    "AU-NCCP-S128-131-LENDING",
                    "AU-PRIV-APP8-CROSSBORDER",
                    "AU-APRA-CPS230-SP",
                    "AU-APRA-CPS220-RMF",
                ]
            },
        },
        "conditional_obligations": {
            "passed": (
                pre_status["AU-PRIV-APP1.7-AUTOMATED"] == ApplicabilityStatus.CONDITIONAL
                and post_status["AU-PRIV-APP1.7-AUTOMATED"] == ApplicabilityStatus.APPLICABLE
                and pre_status["AU-PRIV-APP8-CROSSBORDER"] == ApplicabilityStatus.CONDITIONAL
                and pre_status["AU-APRA-CPS230-BCP"] == ApplicabilityStatus.UNDETERMINED
            ),
            "app1_7_before_2026_12_10": pre_status["AU-PRIV-APP1.7-AUTOMATED"].value,
            "app1_7_on_or_after_2026_12_10": post_status["AU-PRIV-APP1.7-AUTOMATED"].value,
            "cross_border_with_third_party_unknown_residency": pre_status["AU-PRIV-APP8-CROSSBORDER"].value,
            "unknown_critical_operation_status": pre_status["AU-APRA-CPS230-BCP"].value,
        },
        "conflicting_policy_and_system_thresholds": {
            "passed": (
                len(threshold_gap_eval.control_conflicts) == 1
                and threshold_gap_eval.control_conflicts[0].severity == "critical"
                and "approval_threshold_aligned" in threshold_gap_eval.control_conflicts[0].missing_facets
                and len(threshold_gap_eval.questionnaire_gaps) == 1
            ),
            "conflict_title": threshold_gap_eval.control_conflicts[0].title,
            "conflict_severity": threshold_gap_eval.control_conflicts[0].severity,
            "conflict_recommendation": threshold_gap_eval.control_conflicts[0].recommendation,
        },
    }

    return {
        "all_passed": all(s["passed"] for s in scenarios.values()),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
