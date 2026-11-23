"""E3.5 Normative Semantics, Evidence Sufficiency & Assurance Decision Integrity Tests."""

from __future__ import annotations

import json
from pathlib import Path

from banking_crosswalk.catalog import load_regulatory_pack, load_unified_control_library
from banking_crosswalk.llm.eval_harness import (
    build_eval_runtime_config,
    evaluate_clause_benchmark,
    evaluate_questionnaire_benchmark,
)
from banking_crosswalk.llm.types import SemanticMatchingMode
from banking_crosswalk.models import (
    ClauseReviewStatus,
    ReconciliationRelationship,
)
from banking_crosswalk.policy import (
    ENTERPRISE_FACET_PATTERNS,
    FACET_TO_UNIFIED_CONTROLS,
    compile_enterprise_baseline,
    extract_enterprise_policy,
)
from banking_crosswalk.reconciliation import (
    GENERIC_TO_CANONICAL_FACET_BRIDGES,
    generate_reconciliation_candidates,
)
from e11_benchmark_dataset import _build_docx_bytes, _build_pdf_bytes
from e35_independent_evaluation_dataset import (
    E35_INDEPENDENT_EVALUATION_CLAUSES,
    E35_INDEPENDENT_QUESTIONNAIRE_CASES,
    compute_e35_dataset_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_E35_DATASET_SHA256 = "4627defe817508957c0a0572ca28f3fc62aaa45f8018ef1c220ef6e131291f43"


def _doc_builder(paragraphs, fmt, title):
    if fmt == "pdf":
        return _build_pdf_bytes(paragraphs, title)
    if fmt == "docx":
        return _build_docx_bytes(paragraphs)
    return ("\n\n".join(paragraphs)).encode("utf-8")


def test_e35_phase1_canonical_facet_bridge_integrity():
    """Phase 1: Verify all facet bridge targets exist in canonical UCL (158 facets), with no dead or whitespace facets."""
    ucl = load_unified_control_library()
    canonical_facet_ids = {f for c in ucl.controls for f in c.control_facets}
    assert len(canonical_facet_ids) == 158

    retired_facets = {
        "human_oversight_and_override_defined",
        "human_oversight_for_high_risk",
        "adverse_impact_intervention_mechanism",
        "bias_and_fairness_testing",
        "ai_inventory_and_classification",
        "ai_use_case_register_maintained",
    }

    for generic_facet, canonical_targets in GENERIC_TO_CANONICAL_FACET_BRIDGES.items():
        assert len(canonical_targets) > 0, f"Bridge for {generic_facet} has empty target tuple"
        for target in canonical_targets:
            assert target == target.strip(), f"Facet bridge target '{target}' has leading/trailing whitespace"
            assert target in canonical_facet_ids, (
                f"Bridge target '{target}' for generic '{generic_facet}' not found in 158 canonical facets"
            )
            assert target not in retired_facets, (
                f"Bridge target '{target}' for generic '{generic_facet}' is a retired pre-v0.2.0 facet"
            )

    # Verify active bridges point to verified v0.2.0 canonical facets
    assert "fairness_and_explainability_metrics_evaluated" in GENERIC_TO_CANONICAL_FACET_BRIDGES["bias_testing"]
    assert "use_case_registered_in_enterprise_ai_inventory" in GENERIC_TO_CANONICAL_FACET_BRIDGES["model_inventory"]
    assert "destruction_or_deidentification_verified" in GENERIC_TO_CANONICAL_FACET_BRIDGES["zero_data_retention"]
    assert "overseas_recipients_and_regions_mapped" in GENERIC_TO_CANONICAL_FACET_BRIDGES["data_sovereignty"]
    assert "approval_logs_retained" in GENERIC_TO_CANONICAL_FACET_BRIDGES["prompt_logging"]

    # Verify approval_logs_retained is wired in policy extraction
    assert "approval_logs_retained" in ENTERPRISE_FACET_PATTERNS
    assert "approval_logs_retained" in FACET_TO_UNIFIED_CONTROLS
    assert "CTRL-DELEGATED-AUTHORITY-THRESHOLD" in FACET_TO_UNIFIED_CONTROLS["approval_logs_retained"]


def test_e35_phase2_case_a_declarative_assertion_handling():
    """Phase 2: Case A — Declarative enterprise requirements recognized as binding assertions, not discretionary."""
    raw_text = (
        "The bank maintains documented information security controls commensurate with the size "
        "and criticality of its information assets and AI models."
    )
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_a_policy.pdf",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]
    assert cls.normative_type == "declarative_assertion"
    assert cls.is_declarative_assertion is True

    # Reconcile against CPS 234 CONTROLS
    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base A",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    cps_dec = next(d for d in decs if d.external_obligation_id == "AU-APRA-CPS234-CONTROLS")
    assert cps_dec.validated_relationship == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    assert cps_dec.dimension_comparison is not None
    assert cps_dec.dimension_comparison.modality_comparison == "declarative_assertion_aligned"


def test_e35_phase2_case_b_explicit_optionality_handling():
    """Phase 2: Case B — Explicit optionality prevents equivalence claims against mandatory obligations."""
    raw_text = (
        "PIA recommendations are documented, but formal closure remains optional at the discretion of the product owner."
    )
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_b_policy.docx",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]
    assert cls.normative_type == "optionality"

    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base B",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    app1_dec = next(d for d in decs if d.external_obligation_id == "AU-PRIV-APP1-GOV")
    assert app1_dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
    assert app1_dec.dimension_comparison is not None
    assert app1_dec.dimension_comparison.modality_comparison == "enterprise_optional_vs_mandatory"


def test_e35_phase2_case_c_indefinite_retention_vs_destruction_conflict():
    """Phase 2: Case C — Indefinite retention creates POTENTIAL_CONFLICT against APP 11.2 destruction duties."""
    raw_text = (
        "Under APP 11, customer personal information must be retained indefinitely and must not be destroyed under any circumstance."
    )
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_c_policy.pdf",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]

    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base C",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    app11_dec = next(d for d in decs if d.external_obligation_id == "AU-PRIV-APP11-SECURITY")
    assert app11_dec.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT


def test_e35_phase2_case_d_protective_prohibition():
    """Phase 2: Case D — Negative prohibitive wording creating pre-execution threshold blocks."""
    raw_text = "AI agents must not execute payments above AUD 500 without prior human approval."
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_d_policy.docx",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]
    assert cls.normative_type == "protective_prohibition"
    assert cls.approval_timing == "pre_execution"

    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base D",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    naic_dec = next(d for d in decs if d.external_obligation_id == "AU-NAIC-AI6-TEST-HUMAN")
    assert naic_dec.validated_relationship == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT


def test_e35_phase2_case_e_post_execution_review_weakening():
    """Phase 2: Case E — Permissive execution before review detected as post_execution and weaker."""
    raw_text = "Payments above AUD 500 may be executed before manager review during peak volume periods."
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_e_policy.docx",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]
    assert cls.approval_timing == "post_execution"

    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base E",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    naic_dec = next(d for d in decs if d.external_obligation_id == "AU-NAIC-AI6-TEST-HUMAN")
    assert naic_dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT


def test_e35_phase2_case_f_unresolved_attachment_reference():
    """Phase 2: Case F — Unresolved internal references ('comply with Annexure D2') resolve to UNDETERMINED."""
    raw_text = "Information security controls must comply with Annexure D2 regarding cloud key management."
    pol = extract_enterprise_policy(
        tenant_id="t-e35",
        name="case_f_policy.pdf",
        text=raw_text,
    )
    assert len(pol.clauses) == 1
    cls = pol.clauses[0]

    approved = [
        cls.model_copy(
            update={
                "review_status": ClauseReviewStatus.APPROVED,
                "control_mappings": [
                    m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                    for m in (cls.control_mappings or [])
                ],
            }
        )
    ]
    pol = pol.model_copy(update={"clauses": approved})
    base = compile_enterprise_baseline(
        tenant_id="t-e35",
        name="Base F",
        policies=[pol],
        created_by="test",
    )
    reg_pack = load_regulatory_pack()
    decs = generate_reconciliation_candidates(
        tenant_id="t-e35",
        enterprise_baseline=base,
        policies=[pol],
        regulatory_pack=reg_pack,
    )
    assert len(decs) == 1
    assert decs[0].external_obligation_id is None
    assert decs[0].validated_relationship == ReconciliationRelationship.UNDETERMINED


def test_e35_phase3_independent_dataset_integrity_and_evaluation():
    """Phase 3: Verify immutable dataset SHA-256 and benchmark evaluation metrics on E3.5 independent dataset."""
    assert len(E35_INDEPENDENT_EVALUATION_CLAUSES) == 30
    assert len(E35_INDEPENDENT_QUESTIONNAIRE_CASES) == 8
    observed_sha = compute_e35_dataset_sha256()
    assert observed_sha == EXPECTED_E35_DATASET_SHA256

    json_path = REPO_ROOT / "E35_INDEPENDENT_EVALUATION_DATASET.json"
    assert json_path.exists()
    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["dataset_sha256"] == EXPECTED_E35_DATASET_SHA256
    assert persisted["n_clauses"] == 30
    assert persisted["n_questionnaire_cases"] == 8

    det_cfg = build_eval_runtime_config(mode=SemanticMatchingMode.DISABLED, provider="mock")
    det_res = evaluate_clause_benchmark(
        E35_INDEPENDENT_EVALUATION_CLAUSES,
        mode=SemanticMatchingMode.DISABLED,
        provider="mock",
        config=det_cfg,
        doc_bytes_builder=_doc_builder,
    )
    assert det_res["recall_at_1"] in {14, 18}
    assert det_res["recall_at_5"] in {18, 26}
    assert det_res["exact_accuracy"] in {12, 14}
    assert det_res["false_conflict"] == 0
    assert det_res["false_coverage"] == 0

    hyb_cfg = build_eval_runtime_config(mode=SemanticMatchingMode.HYBRID, provider="mock")
    hyb_res = evaluate_clause_benchmark(
        E35_INDEPENDENT_EVALUATION_CLAUSES,
        mode=SemanticMatchingMode.HYBRID,
        provider="mock",
        config=hyb_cfg,
        doc_bytes_builder=_doc_builder,
    )
    assert hyb_res["recall_at_1"] in {14, 17}
    assert hyb_res["recall_at_5"] in {19, 25}
    assert hyb_res["exact_accuracy"] in {16, 17}
    assert hyb_res["false_positive_coverage_proposals"] == 0
    assert hyb_res["false_conflict"] == 0
    assert hyb_res["false_coverage"] == 0

    q_res = evaluate_questionnaire_benchmark(
        E35_INDEPENDENT_QUESTIONNAIRE_CASES,
        mode=SemanticMatchingMode.DISABLED,
        provider="mock",
        config=det_cfg,
    )
    assert q_res["ho_r1"] == 5
    assert q_res["ho_r3"] == 6
