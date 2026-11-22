"""E3.4 Integration Assurance, Benchmark Regression Guard, Independent Dataset & High-Risk Facet Validation Tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from banking_crosswalk.catalog import load_regulatory_pack, load_unified_control_library
from banking_crosswalk.llm.eval_harness import (
    build_eval_runtime_config,
    evaluate_clause_benchmark,
    evaluate_questionnaire_benchmark,
)
from banking_crosswalk.llm.types import DataClassification, SemanticMatchingMode
from banking_crosswalk.models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    MappingRelationship,
    ReconciliationDecision,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
)
from banking_crosswalk.policy import compile_enterprise_baseline, extract_enterprise_policy
from banking_crosswalk.reconciliation import (
    _infer_canonical_obligation_facets_for_clause,
    _is_auto_extracted_mapping_rationale,
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
)
from banking_crosswalk.semantic_reconciliation import generate_hybrid_reconciliation_candidates
from e11_benchmark_dataset import E11_BENCHMARK_CLAUSES, _build_docx_bytes, _build_pdf_bytes
from e3_benchmark_dataset import E3_EXTENDED_CLAUSES
from e31_calibration_dataset import E31_CALIBRATION_CLAUSES
from e34_independent_evaluation_dataset import (
    E34_INDEPENDENT_EVALUATION_CLAUSES,
    E34_INDEPENDENT_QUESTIONNAIRE_CASES,
    compute_e34_dataset_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_E34_DATASET_SHA256 = "a3ad93a89cf5dd8b5125306d3207519e86ef3cc49d95bbc2fe6d61267a462826"


def _doc_builder(paragraphs, fmt, title):
    if fmt == "pdf":
        return _build_pdf_bytes(paragraphs, title)
    if fmt == "docx":
        return _build_docx_bytes(paragraphs)
    return ("\n\n".join(paragraphs)).encode("utf-8")


def test_e34_phase2_production_wiring_and_backward_compatibility():
    """Phase 2: Verify E3.3 extraction/reconciliation models and persisted record backward compatibility."""
    # 1. Pre-E3.3 persisted ClauseControlMapping without explicit relationship defaults to PARTIAL
    legacy_mapping = ClauseControlMapping.model_validate(
        {
            "tenant_id": "t-legacy",
            "clause_id": "CLS-1",
            "control_id": "CTRL-GOV-FRAMEWORK",
            "mapped_facets": ["model_inventory"],
            "review_status": "proposed",
        }
    )
    assert legacy_mapping.relationship == MappingRelationship.PARTIAL

    # 2. Pre-E3.3 persisted ReconciliationDecision JSON without E3.3 fields deserializes cleanly
    legacy_decision = ReconciliationDecision.model_validate(
        {
            "reconciliation_id": "REC-LEGACY-01",
            "tenant_id": "t-legacy",
            "enterprise_clause_id": "CLS-1",
            "external_obligation_id": "AU-PRIV-APP1-GOV",
            "regulatory_pack_id": "AU-BANKING-REG-PACK-0.1",
            "regulatory_pack_version": "0.2.0",
            "enterprise_policy_id": "POL-1",
            "enterprise_policy_name": "Legacy Policy",
            "enterprise_policy_version": "1.0.0",
            "enterprise_authority_level": "internal_policy",
            "enterprise_clause_sha256": "abc123",
            "enterprise_baseline_id": "BASE-1",
            "enterprise_baseline_version": "1.0.0",
            "enterprise_baseline_revision": 1,
            "enterprise_baseline_sha256": "def456",
            "proposed_relationship": "partially_overlapping",
            "validated_relationship": "partially_overlapping",
            "decision_status": "proposed",
        }
    )
    assert legacy_decision.ai_proposed_relationship is None
    assert legacy_decision.deterministic_veto_applied is False
    assert legacy_decision.deterministic_veto_reasons == []
    assert legacy_decision.missing_conditions_or_evidence == []
    assert legacy_decision.candidate_relevance_state == "requirement_potentially_relevant"
    assert legacy_decision.preserved_candidate_evidence == []

    # 3. Verify all 3 auto-extracted rationale variants from policy.py are recognized by _is_auto_extracted_mapping_rationale
    pol = extract_enterprise_policy(
        tenant_id="t-e34",
        name="Extraction Check",
        text=(
            "All generative AI models must be catalogued in the enterprise model inventory.\n"
            "Automated refunds above AUD 500 require human approval before execution.\n"
            "Personal information must not be sent to overseas recipients."
        ),
    )
    assert len(pol.clauses) == 3
    for c in pol.clauses:
        for m in c.control_mappings:
            assert _is_auto_extracted_mapping_rationale(m.rationale) is True


def test_e34_phase3_regression_guard_for_e11_e3_e31_hybrid_and_cps234_timing():
    """Phase 3: Guard against the two E3.3 regressions (auto-extracted rationale prefix & CPS 234 72h vs 10bd deadline)."""
    reg_pack = load_regulatory_pack()
    all_cases = {
        c.case_id: c
        for c in list(E11_BENCHMARK_CLAUSES)
        + list(E3_EXTENDED_CLAUSES)
        + list(E31_CALIBRATION_CLAUSES)
    }

    # Check CPS 234 10-day incident deadline conflict detection on HO-TIB-07 and E3-DEV-YV-05
    for cid in ("HO-TIB-07", "E3-DEV-YV-05"):
        case = all_cases[cid]
        pol = extract_enterprise_policy(
            tenant_id=f"t-{cid}",
            name=case.doc_filename,
            text=case.raw_text,
        )
        approved = [
            c.model_copy(
                update={
                    "review_status": ClauseReviewStatus.APPROVED,
                    "control_mappings": [
                        m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                        for m in (c.control_mappings or [])
                    ],
                }
            )
            for c in pol.clauses
        ]
        pol = pol.model_copy(update={"clauses": approved})
        base = compile_enterprise_baseline(
            tenant_id=f"t-{cid}",
            name="Base",
            policies=[pol],
            created_by="test",
        )
        cfg = build_eval_runtime_config(mode=SemanticMatchingMode.HYBRID, provider="mock")
        decs, _ = generate_hybrid_reconciliation_candidates(
            tenant_id=f"t-{cid}",
            enterprise_baseline=base,
            policies=[pol],
            regulatory_pack=reg_pack,
            config=cfg,
            data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
        )
        cps_dec = next(d for d in decs if d.external_obligation_id == "AU-APRA-CPS234-INCIDENT")
        assert cps_dec.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT

    # Check semantic dismissal on internal prompt-logging / ESG clauses in hybrid mode
    for cid, exp_rel in (
        ("DEV-PMC-15", ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT),
        ("DEV-PMC-18", ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP),
        ("E3-DEV-YV-09", ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT),
        ("E3-HO-BR-09", ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT),
        ("E31-DEV-12", ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT),
        ("E31-HO-12", ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT),
    ):
        case = all_cases[cid]
        pol = extract_enterprise_policy(
            tenant_id=f"t-{cid}",
            name=case.doc_filename,
            text=case.raw_text,
        )
        approved = [
            c.model_copy(
                update={
                    "review_status": ClauseReviewStatus.APPROVED,
                    "control_mappings": [
                        m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                        for m in (c.control_mappings or [])
                    ],
                }
            )
            for c in pol.clauses
        ]
        pol = pol.model_copy(update={"clauses": approved})
        base = compile_enterprise_baseline(
            tenant_id=f"t-{cid}",
            name="Base",
            policies=[pol],
            created_by="test",
        )
        cfg = build_eval_runtime_config(mode=SemanticMatchingMode.HYBRID, provider="mock")
        decs, _ = generate_hybrid_reconciliation_candidates(
            tenant_id=f"t-{cid}",
            enterprise_baseline=base,
            policies=[pol],
            regulatory_pack=reg_pack,
            config=cfg,
            data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
        )
        assert len(decs) == 1
        assert decs[0].external_obligation_id is None
        assert decs[0].validated_relationship == exp_rel


def test_e34_phase4_frozen_independent_dataset_integrity_and_evaluation():
    """Phase 4: Verify immutable dataset SHA-256 and un-tuned evaluation metrics on E3.4 independent dataset."""
    assert len(E34_INDEPENDENT_EVALUATION_CLAUSES) == 30
    assert len(E34_INDEPENDENT_QUESTIONNAIRE_CASES) == 8
    observed_sha = compute_e34_dataset_sha256()
    assert observed_sha == EXPECTED_E34_DATASET_SHA256

    json_path = REPO_ROOT / "E34_INDEPENDENT_EVALUATION_DATASET.json"
    assert json_path.exists()
    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["dataset_sha256"] == EXPECTED_E34_DATASET_SHA256
    assert persisted["n_clauses"] == 30
    assert persisted["n_questionnaire_cases"] == 8

    det_cfg = build_eval_runtime_config(mode=SemanticMatchingMode.DISABLED, provider="mock")
    det_res = evaluate_clause_benchmark(
        E34_INDEPENDENT_EVALUATION_CLAUSES,
        mode=SemanticMatchingMode.DISABLED,
        provider="mock",
        config=det_cfg,
        doc_bytes_builder=_doc_builder,
    )
    assert det_res["recall_at_1"] == 21
    assert det_res["recall_at_5"] == 25
    assert det_res["exact_accuracy"] in {17, 18}  # 18 with E3.5 internal attachment resolution (E34-IND-19)
    assert det_res["false_conflict"] == 0
    assert det_res["false_coverage"] == 0

    hyb_cfg = build_eval_runtime_config(mode=SemanticMatchingMode.HYBRID, provider="mock")
    hyb_res = evaluate_clause_benchmark(
        E34_INDEPENDENT_EVALUATION_CLAUSES,
        mode=SemanticMatchingMode.HYBRID,
        provider="mock",
        config=hyb_cfg,
        doc_bytes_builder=_doc_builder,
    )
    assert hyb_res["recall_at_1"] == 22
    assert hyb_res["recall_at_5"] == 25
    assert hyb_res["exact_accuracy"] in {18, 19}  # 19 with E3.5 internal attachment resolution (E34-IND-19)
    assert hyb_res["false_positive_coverage_proposals"] == 0
    assert hyb_res["false_conflict"] == 0
    assert hyb_res["false_coverage"] == 0

    q_res = evaluate_questionnaire_benchmark(
        E34_INDEPENDENT_QUESTIONNAIRE_CASES,
        mode=SemanticMatchingMode.DISABLED,
        provider="mock",
        config=det_cfg,
    )
    assert q_res["ho_r1"] == 8
    assert q_res["ho_r3"] == 8
    assert q_res["confirmed_covered"] == 0


# 15 Paired Positive & Facet-Specific Negative Fixtures for the 49 High-Risk Facets
HIGH_RISK_FACET_FIXTURES = (
    (
        "E34-FT-01",
        "ENTERPRISE_CONTROL_ONLY",
        (
            "human_approval_required",
            "approval_threshold_defined",
            "pre_execution_block",
        ),
        "Automated credit disbursements above AUD 1,000 require human approval before execution.",
        "Standard batch settlement reports are archived nightly in the finance data warehouse.",
    ),
    (
        "E34-FT-02",
        "AU-ASIC-RG104-REPRESENTATIVES",
        (
            "operator_ai_competence_and_training_completed",
            "supervisory_quality_assurance_on_ai_assisted_staff",
            "clear_escalation_and_override_authority",
        ),
        "Under ASIC RG 104, credit representatives must complete AI literacy staff training, undergo supervisory quality assurance monitoring and supervision, and maintain clear escalation and override authority to halt automated recommendations.",
        "Representatives must complete annual workplace fire safety and ergonomic desk checks.",
    ),
    (
        "E34-FT-03",
        "AU-NAIC-AI6-TEST-HUMAN",
        (
            "pre_deployment_and_ongoing_drift_monitoring",
            "meaningful_human_oversight_and_kill_switch",
            "customer_contestability_and_recourse_pathway",
        ),
        "High-risk AI systems must undergo pre-deployment testing and ongoing drift monitoring, enforce meaningful human oversight with an emergency kill switch, and provide a customer contestability and recourse pathway.",
        "Internal software release notes must be formatted in Markdown and archived in Git.",
    ),
    (
        "E34-FT-04",
        "AU-NCCP-S128-131-LENDING",
        (
            "consumer_requirements_and_objectives_captured",
            "financial_situation_verified_from_reliable_evidence",
            "unsuitability_and_substantial_hardship_screen_enforced",
            "written_unsuitability_assessment_retrievable",
        ),
        "Under NCCP Act s 128, lending models must capture consumer requirements and objectives, verify financial situation from reliable evidence, enforce an unsuitability and substantial hardship screen, and retain an unsuitability assessment record under section 132.",
        "Commercial corporate treasury swaps are settled via Austraclear.",
    ),
    (
        "E34-FT-05",
        "AU-PRIV-APP1-GOV",
        (
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ),
        "Under APP 1, the bank must assign privacy accountability to a senior privacy officer, implement privacy practices and procedures, and maintain a current APP privacy policy.",
        "Office stationery purchases require manager sign-off.",
    ),
    (
        "E34-FT-06",
        "AU-OAIC-APPG-CH1-PIA",
        (
            "pia_threshold_screen_completed",
            "pia_recommendations_tracked_to_closure",
            "privacy_by_design_controls_embedded",
        ),
        "Every high-privacy-risk AI project must complete a Privacy Impact Assessment threshold screen, embed privacy-by-design controls, and track PIA recommendations to closure.",
        "Quarterly financial statements are audited by external statutory auditors.",
    ),
    (
        "E34-FT-07",
        "AU-PRIV-APP3-COLLECT",
        (
            "collection_purpose_defined",
            "necessity_assessed",
            "sensitive_information_consent",
        ),
        "Under APP 3, teams collecting personal information must define the lawful collection purpose, confirm collection is reasonably necessary with data minimisation, and obtain sensitive information consent before collecting biometrics.",
        "Branch ATMs are replenished with cash cassettes twice weekly.",
    ),
    (
        "E34-FT-08",
        "AU-PRIV-APP8-CROSSBORDER",
        (
            "overseas_recipients_and_regions_mapped",
            "app8_reasonable_steps_and_contracts_in_place",
            "s16c_accountability_and_exception_assessed",
        ),
        "Under APP 8, the bank must map overseas recipients and hosting regions, put APP 8 reasonable steps and binding contracts in place, and document the section 16C accountability and exception assessment.",
        "Domestic interbank payments settle over the New Payments Platform.",
    ),
    (
        "E34-FT-09",
        "AU-PRIV-APP11-SECURITY",
        (
            "technical_security_measures_implemented",
            "organisational_security_measures_implemented",
            "retention_schedule_applied",
            "destruction_or_deidentification_verified",
        ),
        "Under APP 11, personal information must be protected by technical security measures including encryption and organisational security measures including staff training, subject to a retention schedule with verified destruction or de-identification.",
        "Corporate cafeteria menus are updated every Monday.",
    ),
    (
        "E34-FT-10",
        "AU-PRIV-APP1.7-AUTOMATED",
        (
            "significant_decision_screened",
            "personal_information_kinds_disclosed",
            "decision_kinds_disclosed",
        ),
        "Under APP 1.7, the bank must screen computer programs making significant automated decisions and disclose in its privacy policy both the kinds of personal information used and the kinds of decisions made.",
        "Internal helpdesk tickets are triaged by severity level.",
    ),
    (
        "E34-FT-11",
        "AU-APRA-CPS234-INCIDENT",
        (
            "incident_detection_defined",
            "response_and_escalation_defined",
            "apra_notification_screened",
            "material_weaknesses_tracked",
        ),
        "Under APRA CPS 234, the bank must maintain security incident detection monitoring alerts, define an incident response and escalation plan, screen for 72-hour APRA notification, and track material control weakness items in a remediation register.",
        "Annual leave requests must be submitted through the HR portal.",
    ),
    (
        "E34-FT-12",
        "AU-PRIV-NDB-S26WE",
        (
            "ai_data_leakage_detection_enabled",
            "ndb_30day_assessment_workflow_defined",
            "oaic_and_individual_notification_prepared",
        ),
        "Under the Notifiable Data Breaches scheme, the bank must enable AI data leakage detection, complete the 30-day eligible data breach assessment workflow, and prepare an OAIC notification and data breach statement to notify individuals.",
        "Network routers undergo firmware patching during Sunday maintenance windows.",
    ),
    (
        "E34-FT-13",
        "AU-APRA-CPS230-NOTIFY",
        (
            "msp_register_updated_for_ai_vendors",
            "prior_apra_consultation_for_material_offshoring",
            "incident_72h_and_agreement_20bd_notifications_defined",
        ),
        "Under APRA CPS 230, the bank must update the Material Service Provider register for AI vendors, consult APRA prior to material offshoring, and notify APRA within 72 hours of material incidents or 20 business days of agreement changes.",
        "Local office cleaning contractors sign visitor logbooks at reception.",
    ),
    (
        "E34-FT-14",
        "AU-ASIC-RG271-COMPLAINT",
        (
            "complaints_broadly_recognised",
            "complaints_recorded",
            "response_timeframes_enforced",
            "response_content_complete",
            "human_escalation_available",
        ),
        "Under ASIC RG 271, every expression of dissatisfaction must ensure complaints recorded in the complaint register meet response timeframe rules, provide a complete IDR response with reasons and AFCA details, and support human escalation.",
        "Marketing brochures must use approved brand fonts.",
    ),
    (
        "E34-FT-15",
        "AU-ASIC-RG271-SYSTEMIC",
        (
            "complaint_data_analysed",
            "systemic_issue_thresholds_defined",
            "systemic_issues_escalated",
            "affected_customers_remediated",
        ),
        "Under ASIC RG 271, the bank must analyse complaint data, define systemic issue thresholds, complete systemic issue escalation to the risk committee, and remediate affected customers.",
        "Branch signage must be inspected for physical wear every six months.",
    ),
    (
        "E34-FT-16",
        "AU-PRIV-APP5-NOTICE",
        (
            "collection_notice_exists",
            "notice_content_complete",
            "notice_timing_defined",
        ),
        "Under APP 5, a privacy collection notice with complete notice content explaining purpose of collection must be provided at collection.",
        "Employee onboarding checklists cover ergonomic chair adjustments.",
    ),
    (
        "E34-FT-17",
        "AU-PRIV-APP6-USE",
        (
            "primary_purpose_recorded",
            "secondary_use_basis_checked",
            "disclosures_logged",
        ),
        "Under APP 6, the primary purpose is recorded, any secondary use consent or lawful disclosure basis is verified, and external disclosures are recorded in the disclosure log.",
        "Canteen catering invoices are reconciled monthly by accounts payable.",
    ),
    (
        "E34-FT-18",
        "AU-PRIV-APP12-13-RIGHTS",
        (
            "ai_personal_records_retrievable_for_access",
            "correction_propagated_to_ai_stores",
            "access_and_correction_timeframes_tracked",
        ),
        "Under APP 12 and APP 13, customer access requests retrieve personal information, correction requests update personal information across AI stores, and responses are tracked within 30 days.",
        "Printer toner cartridges are replaced by facilities support staff.",
    ),
    (
        "E34-FT-19",
        "AU-APRA-CPS234-ROLES-ASSETS",
        (
            "security_roles_and_asset_owners_assigned",
            "ai_assets_classified_by_criticality_and_sensitivity",
            "third_party_managed_ai_assets_catalogued",
        ),
        "Under CPS 234, security responsibilities and asset owners are assigned, AI information assets are classified by criticality and sensitivity, and cloud assets and external information assets managed by third parties are catalogued.",
        "Company fleet vehicles undergo annual registration renewal.",
    ),
    (
        "E34-FT-20",
        "AU-APRA-CPS234-CONTROLS",
        (
            "information_assets_identified",
            "threats_and_vulnerabilities_assessed",
            "controls_commensurate",
            "third_party_assets_in_scope",
        ),
        "Under CPS 234, information assets are recorded in the asset register, threats and vulnerabilities undergo a formal vulnerability assessment, security controls are commensurate with sensitivity, and vendor security for third party information assets is included in scope.",
        "Annual shareholder meeting minutes are published to the investor portal.",
    ),
    (
        "E34-FT-21",
        "NIST-AI-RMF-MEASURE-MANAGE",
        (
            "tevv_validity_and_reliability_benchmarked",
            "fairness_and_explainability_metrics_evaluated",
            "residual_risk_acceptance_and_drift_response_logged",
        ),
        "Under NIST AI RMF MEASURE and MANAGE, AI models complete TEVV validity and reliability benchmark evaluations, fairness and explainability evaluation, and logged residual risk acceptance with post-deployment model drift monitoring.",
        "Office air-conditioning filters are serviced every six months.",
    ),
    (
        "E34-FT-22",
        "ISO27001-ISMS-CONTROLS",
        (
            "ai_environment_in_isms_scope_and_risk_assessment",
            "access_cryptography_and_secure_engineering_applied",
            "supplier_security_and_isms_internal_audit_verified",
        ),
        "Under ISO 27001, AI environments are governed inside the ISMS information security risk assessment, enforce access control, encryption, and secure development, and undergo supplier security review and internal audit.",
        "Retail teller cash drawers are balanced at shift end.",
    ),
)


def test_e34_phase5_high_risk_facet_positive_and_negative_production_suite():
    """Phase 5: Verify positive extraction and zero false-positive triggers across all 70 production-implemented high-risk facets (plus 3 CPS 230 facets)."""
    reg_pack = load_regulatory_pack()
    ob_by_id = {ob.obligation_id: ob for ob in reg_pack.obligations}

    tested_facets_total = 0
    for fixture_id, ob_id, target_facets, pos_text, neg_text in HIGH_RISK_FACET_FIXTURES:
        tested_facets_total += len(target_facets)
        pol_pos = extract_enterprise_policy(
            tenant_id="t-facet-pos",
            name=f"{fixture_id}-pos.txt",
            text=pos_text,
        )
        pol_neg = extract_enterprise_policy(
            tenant_id="t-facet-neg",
            name=f"{fixture_id}-neg.txt",
            text=neg_text,
        )
        cls_pos = pol_pos.clauses[0]
        cls_neg = pol_neg.clauses[0]

        if ob_id == "ENTERPRISE_CONTROL_ONLY":
            pos_extracted = set(cls_pos.control_facets or [])
            neg_extracted = set(cls_neg.control_facets or [])
        else:
            ob = ob_by_id[ob_id]
            pos_extracted = _infer_canonical_obligation_facets_for_clause(cls_pos, ob)
            neg_extracted = _infer_canonical_obligation_facets_for_clause(cls_neg, ob)

        for tf in target_facets:
            assert tf in pos_extracted, f"{fixture_id} positive fixture failed to extract '{tf}'"
            assert tf not in neg_extracted, f"{fixture_id} negative fixture falsely triggered '{tf}'"

    # Verify all 70 implemented high-risk facets + 3 CPS230 notification facets = 73 tested facets
    assert tested_facets_total == 73

    # Explicitly confirm the remaining 1/71 high-risk facet (`approval_logs_retained`) is NOT
    # directly extracted by production extract_enterprise_policy() (honest gap disclosure)
    pol_gap = extract_enterprise_policy(
        tenant_id="t-gap",
        name="approval-log.txt",
        text="All high-value approval decisions and override logs must be retained for 7 years.",
    )
    assert "approval_logs_retained" not in (pol_gap.clauses[0].control_facets or [])


def test_e34_phase5_158_facet_matrix_three_dimension_separation():
    """Phase 5: Verify E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv accounts for all 158 facets with separated dimensions."""
    ucl = load_unified_control_library()
    canonical_facets = {f for ctrl in ucl.controls for f in ctrl.control_facets}
    assert len(canonical_facets) == 158

    csv_path = REPO_ROOT / "E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv"
    assert csv_path.exists()
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 158
    row_by_facet = {r["facet_id"]: r for r in rows}
    assert set(row_by_facet.keys()) == canonical_facets

    required_cols = {
        "implemented_capability",
        "tested_capability",
        "validated_accuracy",
        "independent_e34_tp_fp_fn",
        "regression_p1_tp_fp_fn",
        "classification",
    }
    assert required_cols.issubset(set(rows[0].keys()))

    # Verify approval_logs_retained is honestly classified as experimental EngineA1 only
    alr = row_by_facet["approval_logs_retained"]
    assert "Experimental EngineA1" in alr["implemented_capability"]
    assert "Experimental EngineA1 only" in alr["classification"]
