#!/usr/bin/env python3
"""Generate E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv dynamically from UNIFIED_CONTROL_LIBRARY.json.

E3.4 Phase 5 Audit Upgrade:
Strictly separates all 158 canonical control facets across three non-conflated dimensions:
  1. Implemented Capability:
     - Production direct extraction (`policy.py:ENTERPRISE_FACET_PATTERNS`)
     - Production generic-to-canonical bridge + obligation facet_keywords (`reconciliation.py`)
     - Production obligation facet_keywords (`reconciliation.py:_infer_canonical_obligation_facets_for_clause`)
     - Experimental EngineA1 & external framework regex only (`engine_a1.py` / `policy.py:GENERIC_FACET_PATTERNS`)
  2. Tested Capability:
     - Tested positive + facet-specific negative (production pipeline unit test suite)
     - Tested positive only (regression dataset)
     - Untested source-code mapping only (0 positive test cases)
  3. Validated Accuracy:
     - Independent E3.4 empirical measurement (small-N, un-tuned frozen dataset)
     - Regression-only measurement (P1 V2 Pack v0.2.0 / Supplemental, not independent)
     - Unvalidated (0 positive evaluation instances)

Never conflates experimental `EngineA1` rules or oracle `expected_controls` hints with
production `policy.py` + `reconciliation.py` extraction performance.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
BACKEND_TESTS_DIR = BACKEND_DIR / "tests"
for p in (REPO_ROOT, BACKEND_DIR, BACKEND_TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from banking_crosswalk.catalog import load_regulatory_pack  # noqa: E402
from banking_crosswalk.policy import (  # noqa: E402
    ENTERPRISE_FACET_PATTERNS,
    GENERIC_FACET_PATTERNS,
    extract_enterprise_policy,
)
from banking_crosswalk.reconciliation import (  # noqa: E402
    GENERIC_TO_CANONICAL_FACET_BRIDGES,
    _infer_canonical_obligation_facets_for_clause,
    rank_reconciliation_candidates_for_clause,
)
from e34_independent_evaluation_dataset import (  # noqa: E402
    E34_CLAUSE_FACET_ANNOTATIONS,
    E34_INDEPENDENT_EVALUATION_CLAUSES,
)
from scripts.experiments.canonical_adapter import CanonicalMappingAdapter  # noqa: E402
from scripts.experiments.engine_a1 import EngineA1  # noqa: E402


HIGH_RISK_DOMAINS = {
    "Human oversight and approval",
    "Privacy and personal information",
    "Information security",
    "Customer complaints and contestability",
    "Monitoring and incident management",
}

# High-risk facets with dedicated positive + facet-specific negative unit tests
# verified in backend/tests/test_e34_integration_and_facet_validation.py
PRODUCTION_UNIT_TESTED_HIGH_RISK_FACETS: dict[str, tuple[str, str]] = {
    # Approval & Human Oversight
    "human_approval_required": ("E34-FT-01-POS", "E34-FT-01-NEG"),
    "approval_threshold_defined": ("E34-FT-01-POS", "E34-FT-01-NEG"),
    "pre_execution_block": ("E34-FT-01-POS", "E34-FT-01-NEG"),
    "operator_ai_competence_and_training_completed": ("E34-FT-02-POS", "E34-FT-02-NEG"),
    "supervisory_quality_assurance_on_ai_assisted_staff": ("E34-FT-02-POS", "E34-FT-02-NEG"),
    "clear_escalation_and_override_authority": ("E34-FT-02-POS", "E34-FT-02-NEG"),
    "pre_deployment_and_ongoing_drift_monitoring": ("E34-FT-03-POS", "E34-FT-03-NEG"),
    "meaningful_human_oversight_and_kill_switch": ("E34-FT-03-POS", "E34-FT-03-NEG"),
    "customer_contestability_and_recourse_pathway": ("E34-FT-03-POS", "E34-FT-03-NEG"),
    "consumer_requirements_and_objectives_captured": ("E34-FT-04-POS", "E34-FT-04-NEG"),
    "financial_situation_verified_from_reliable_evidence": ("E34-FT-04-POS", "E34-FT-04-NEG"),
    "unsuitability_and_substantial_hardship_screen_enforced": ("E34-FT-04-POS", "E34-FT-04-NEG"),
    "written_unsuitability_assessment_retrievable": ("E34-FT-04-POS", "E34-FT-04-NEG"),
    # Privacy & Personal Information
    "privacy_accountability_assigned": ("E34-FT-05-POS", "E34-FT-05-NEG"),
    "privacy_practices_implemented": ("E34-FT-05-POS", "E34-FT-05-NEG"),
    "privacy_policy_current": ("E34-FT-05-POS", "E34-FT-05-NEG"),
    "pia_threshold_screen_completed": ("E34-FT-06-POS", "E34-FT-06-NEG"),
    "pia_recommendations_tracked_to_closure": ("E34-FT-06-POS", "E34-FT-06-NEG"),
    "privacy_by_design_controls_embedded": ("E34-FT-06-POS", "E34-FT-06-NEG"),
    "collection_purpose_defined": ("E34-FT-07-POS", "E34-FT-07-NEG"),
    "necessity_assessed": ("E34-FT-07-POS", "E34-FT-07-NEG"),
    "sensitive_information_consent": ("E34-FT-07-POS", "E34-FT-07-NEG"),
    "overseas_recipients_and_regions_mapped": ("E34-FT-08-POS", "E34-FT-08-NEG"),
    "app8_reasonable_steps_and_contracts_in_place": ("E34-FT-08-POS", "E34-FT-08-NEG"),
    "s16c_accountability_and_exception_assessed": ("E34-FT-08-POS", "E34-FT-08-NEG"),
    "technical_security_measures_implemented": ("E34-FT-09-POS", "E34-FT-09-NEG"),
    "organisational_security_measures_implemented": ("E34-FT-09-POS", "E34-FT-09-NEG"),
    "retention_schedule_applied": ("E34-FT-09-POS", "E34-FT-09-NEG"),
    "destruction_or_deidentification_verified": ("E34-FT-09-POS", "E34-FT-09-NEG"),
    "significant_decision_screened": ("E34-FT-10-POS", "E34-FT-10-NEG"),
    "personal_information_kinds_disclosed": ("E34-FT-10-POS", "E34-FT-10-NEG"),
    "decision_kinds_disclosed": ("E34-FT-10-POS", "E34-FT-10-NEG"),
    # Incident Reporting, Security & Monitoring
    "incident_detection_defined": ("E34-FT-11-POS", "E34-FT-11-NEG"),
    "response_and_escalation_defined": ("E34-FT-11-POS", "E34-FT-11-NEG"),
    "apra_notification_screened": ("E34-FT-11-POS", "E34-FT-11-NEG"),
    "material_weaknesses_tracked": ("E34-FT-11-POS", "E34-FT-11-NEG"),
    "ai_data_leakage_detection_enabled": ("E34-FT-12-POS", "E34-FT-12-NEG"),
    "ndb_30day_assessment_workflow_defined": ("E34-FT-12-POS", "E34-FT-12-NEG"),
    "oaic_and_individual_notification_prepared": ("E34-FT-12-POS", "E34-FT-12-NEG"),
    "msp_register_updated_for_ai_vendors": ("E34-FT-13-POS", "E34-FT-13-NEG"),
    "prior_apra_consultation_for_material_offshoring": ("E34-FT-13-POS", "E34-FT-13-NEG"),
    "incident_72h_and_agreement_20bd_notifications_defined": ("E34-FT-13-POS", "E34-FT-13-NEG"),
    # Customer Complaints & Contestability
    "complaints_broadly_recognised": ("E34-FT-14-POS", "E34-FT-14-NEG"),
    "complaints_recorded": ("E34-FT-14-POS", "E34-FT-14-NEG"),
    "response_timeframes_enforced": ("E34-FT-14-POS", "E34-FT-14-NEG"),
    "response_content_complete": ("E34-FT-14-POS", "E34-FT-14-NEG"),
    "human_escalation_available": ("E34-FT-14-POS", "E34-FT-14-NEG"),
    "complaint_data_analysed": ("E34-FT-15-POS", "E34-FT-15-NEG"),
    "systemic_issue_thresholds_defined": ("E34-FT-15-POS", "E34-FT-15-NEG"),
    "systemic_issues_escalated": ("E34-FT-15-POS", "E34-FT-15-NEG"),
    "affected_customers_remediated": ("E34-FT-15-POS", "E34-FT-15-NEG"),
    # Remaining High-Risk Notice, Use/Disclosure, Access/Correction, InfoSec, Drift & ISMS
    "collection_notice_exists": ("E34-FT-16-POS", "E34-FT-16-NEG"),
    "notice_content_complete": ("E34-FT-16-POS", "E34-FT-16-NEG"),
    "notice_timing_defined": ("E34-FT-16-POS", "E34-FT-16-NEG"),
    "primary_purpose_recorded": ("E34-FT-17-POS", "E34-FT-17-NEG"),
    "secondary_use_basis_checked": ("E34-FT-17-POS", "E34-FT-17-NEG"),
    "disclosures_logged": ("E34-FT-17-POS", "E34-FT-17-NEG"),
    "ai_personal_records_retrievable_for_access": ("E34-FT-18-POS", "E34-FT-18-NEG"),
    "correction_propagated_to_ai_stores": ("E34-FT-18-POS", "E34-FT-18-NEG"),
    "access_and_correction_timeframes_tracked": ("E34-FT-18-POS", "E34-FT-18-NEG"),
    "security_roles_and_asset_owners_assigned": ("E34-FT-19-POS", "E34-FT-19-NEG"),
    "ai_assets_classified_by_criticality_and_sensitivity": ("E34-FT-19-POS", "E34-FT-19-NEG"),
    "third_party_managed_ai_assets_catalogued": ("E34-FT-19-POS", "E34-FT-19-NEG"),
    "information_assets_identified": ("E34-FT-20-POS", "E34-FT-20-NEG"),
    "threats_and_vulnerabilities_assessed": ("E34-FT-20-POS", "E34-FT-20-NEG"),
    "controls_commensurate": ("E34-FT-20-POS", "E34-FT-20-NEG"),
    "third_party_assets_in_scope": ("E34-FT-20-POS", "E34-FT-20-NEG"),
    "tevv_validity_and_reliability_benchmarked": ("E34-FT-21-POS", "E34-FT-21-NEG"),
    "fairness_and_explainability_metrics_evaluated": ("E34-FT-21-POS", "E34-FT-21-NEG"),
    "residual_risk_acceptance_and_drift_response_logged": ("E34-FT-21-POS", "E34-FT-21-NEG"),
    "ai_environment_in_isms_scope_and_risk_assessment": ("E34-FT-22-POS", "E34-FT-22-NEG"),
    "access_cryptography_and_secure_engineering_applied": ("E34-FT-22-POS", "E34-FT-22-NEG"),
    "supplier_security_and_isms_internal_audit_verified": ("E34-FT-22-POS", "E34-FT-22-NEG"),
}


def _extract_production_canonical_facets_for_text(
    text: str,
    reg_pack: Any,
    canonical_facets: set[str],
    top_k_obligations: int = 2,
) -> set[str]:
    """Run the actual production extraction & candidate-ranking pipeline without oracle control hints."""
    pol = extract_enterprise_policy(
        tenant_id="facet-audit",
        name="audit_clause.txt",
        text=text,
        created_by="facet-audit",
    )
    if not pol.clauses:
        return set()
    clause = pol.clauses[0]
    extracted: set[str] = set(clause.control_facets or []) & canonical_facets
    ranked = rank_reconciliation_candidates_for_clause(
        clause=clause,
        regulatory_pack=reg_pack,
        top_k=top_k_obligations,
    )
    for cand in ranked:
        if cand["score"] >= 0.30 and (cand["inferred_facets"] or cand["topic_matched"]):
            ob = cand["obligation"]
            extracted.update(
                _infer_canonical_obligation_facets_for_clause(clause, ob) & canonical_facets
            )
    return extracted


def build_facet_coverage_matrix(output_path: Path | None = None) -> dict[str, Any]:
    adapter = CanonicalMappingAdapter(REPO_ROOT / "UNIFIED_CONTROL_LIBRARY.json")
    engine_a1 = EngineA1(REPO_ROOT / "UNIFIED_CONTROL_LIBRARY.json")

    ucl = json.loads((REPO_ROOT / "UNIFIED_CONTROL_LIBRARY.json").read_text(encoding="utf-8"))
    cat = json.loads((REPO_ROOT / "ATOMIC_OBLIGATION_CATALOGUE.json").read_text(encoding="utf-8"))
    v2_v020 = json.loads(
        (REPO_ROOT / "P1_EVALUATION_DATASET_V2_PACK_V020.json").read_text(encoding="utf-8")
    )
    supp = json.loads(
        (REPO_ROOT / "P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json").read_text(encoding="utf-8")
    )

    reg_pack = load_regulatory_pack()
    canonical_set = {f for ctrl in ucl["controls"] for f in ctrl.get("control_facets", [])}

    obligations = cat["obligations"]
    facet_to_obs: dict[str, list[str]] = {}
    facet_to_keywords: dict[str, list[str]] = {}
    for ob in obligations:
        oid = ob["obligation_id"]
        kw_map = ob.get("facet_keywords", {})
        for f in ob.get("coverage_facets", []):
            facet_to_obs.setdefault(f, []).append(oid)
            for kw in kw_map.get(f, []):
                if kw not in facet_to_keywords.setdefault(f, []):
                    facet_to_keywords[f].append(kw)

    bridged_from_generic: dict[str, list[str]] = {}
    for gen_f, canon_list in GENERIC_TO_CANONICAL_FACET_BRIDGES.items():
        for cf in canon_list:
            bridged_from_generic.setdefault(cf, []).append(f"reconciliation:{gen_f}")
    for gen_f, canon_list in adapter.FACET_TRANSLATIONS.items():
        for cf in canon_list:
            tag = f"adapter:{gen_f}"
            if tag not in bridged_from_generic.setdefault(cf, []):
                bridged_from_generic[cf].append(tag)
    for ret_f, spec in adapter.RETIRED_FACET_DECOMPOSITIONS.items():
        for cf in spec["candidates"]:
            tag = f"v020_decomposed:{ret_f}"
            if tag not in bridged_from_generic.setdefault(cf, []):
                bridged_from_generic[cf].append(tag)

    # 1. Production pipeline evaluation on P1 V2 Pack v0.2.0 (156) + Supplemental (36) [Regression Only]
    reg_cases = list(v2_v020["cases"]) + list(supp["cases"])
    reg_pos_ids: dict[str, list[str]] = {}
    reg_neg_fp_ids: dict[str, list[str]] = {}
    reg_tp: dict[str, int] = {}
    reg_fp: dict[str, int] = {}
    reg_fn: dict[str, int] = {}

    for case in reg_cases:
        cid = case["case_id"]
        text = case["input_text"]
        exp_facets = set(case.get("expected_facets", [])) & canonical_set
        beh = case.get("expected_candidate_behavior", "should_generate_candidates")

        pred_facets = _extract_production_canonical_facets_for_text(
            text, reg_pack, canonical_set, top_k_obligations=2
        )

        for ef in exp_facets:
            reg_pos_ids.setdefault(ef, []).append(cid)
            if ef in pred_facets:
                reg_tp[ef] = reg_tp.get(ef, 0) + 1
            else:
                reg_fn[ef] = reg_fn.get(ef, 0) + 1

        for pf in pred_facets:
            if pf not in exp_facets:
                reg_fp[pf] = reg_fp.get(pf, 0) + 1
                if beh == "must_not_generate_candidates":
                    reg_neg_fp_ids.setdefault(pf, []).append(cid)

    # 2. Production pipeline evaluation on Frozen E3.4 Independent Dataset (30 clauses) [Independent Data]
    ann_by_id = {a.case_id: a for a in E34_CLAUSE_FACET_ANNOTATIONS}
    ind_pos_ids: dict[str, list[str]] = {}
    ind_tp: dict[str, int] = {}
    ind_fp: dict[str, int] = {}
    ind_fn: dict[str, int] = {}

    for c in E34_INDEPENDENT_EVALUATION_CLAUSES:
        ann = ann_by_id[c.case_id]
        exp_facets = set(ann.expected_canonical_facets) & canonical_set
        top_k_obs = 2 if len(c.expected_obligation_ids) > 1 else 1
        pred_facets = _extract_production_canonical_facets_for_text(
            c.raw_text, reg_pack, canonical_set, top_k_obligations=top_k_obs
        )
        for ef in exp_facets:
            ind_pos_ids.setdefault(ef, []).append(c.case_id)
            if ef in pred_facets:
                ind_tp[ef] = ind_tp.get(ef, 0) + 1
            else:
                ind_fn[ef] = ind_fn.get(ef, 0) + 1
        for pf in pred_facets:
            if pf not in exp_facets:
                ind_fp[pf] = ind_fp.get(pf, 0) + 1

    rows: list[dict[str, str]] = []
    class_counts: dict[str, int] = {}
    impl_counts: dict[str, int] = {}
    test_counts: dict[str, int] = {}
    val_counts: dict[str, int] = {}

    for ctrl in ucl["controls"]:
        ctrl_id = ctrl["control_id"]
        domain = ctrl["domain"]
        ev_reqs = (
            "; ".join(ctrl.get("evidence_requirements", [])[:2])
            or "Documented policy and control evidence"
        )

        for facet in ctrl.get("control_facets", []):
            obs = facet_to_obs.get(facet, [])
            kws = facet_to_keywords.get(facet, [])
            in_enterprise_direct = facet in ENTERPRISE_FACET_PATTERNS
            in_generic_external_only = (
                facet in GENERIC_FACET_PATTERNS and not in_enterprise_direct
            )
            in_a1_direct = facet in engine_a1.FACET_REGEX_PATTERNS
            has_ob_kw = len(kws) > 0
            prod_bridges = [
                b for b in bridged_from_generic.get(facet, []) if b.startswith("reconciliation:")
            ]
            all_bridges = bridged_from_generic.get(facet, [])

            # Dimension 1: Implemented Capability
            if in_enterprise_direct:
                implemented_capability = "Production direct extraction (policy.py ENTERPRISE_FACET_PATTERNS)"
            elif prod_bridges and has_ob_kw:
                implemented_capability = "Production generic bridge + obligation facet_keywords (reconciliation.py)"
            elif has_ob_kw:
                implemented_capability = "Production obligation facet_keywords (reconciliation.py)"
            elif in_a1_direct or in_generic_external_only:
                implemented_capability = "Experimental EngineA1 & external framework regex only (not in production clause extractor)"
            else:
                implemented_capability = "Unimplemented"

            # Dimension 2: Tested Capability
            unit_pair = PRODUCTION_UNIT_TESTED_HIGH_RISK_FACETS.get(facet)
            r_pos = reg_pos_ids.get(facet, [])
            i_pos = ind_pos_ids.get(facet, [])
            if unit_pair is not None:
                tested_capability = "Tested positive + facet-specific negative (production unit tests)"
            elif r_pos or i_pos:
                tested_capability = "Tested positive only (benchmark/regression clauses)"
            else:
                tested_capability = "Untested source-code mapping only (0 labelled positive cases)"

            # Dimension 3: Validated Accuracy
            itp = ind_tp.get(facet, 0)
            ifp = ind_fp.get(facet, 0)
            ifn = ind_fn.get(facet, 0)
            rtp = reg_tp.get(facet, 0)
            rfp = reg_fp.get(facet, 0)
            rfn = reg_fn.get(facet, 0)

            ind_prec = f"{itp / (itp + ifp):.2f}" if (itp + ifp) > 0 else "N/A"
            ind_rec = f"{itp / (itp + ifn):.2f}" if (itp + ifn) > 0 else "N/A"
            reg_prec = f"{rtp / (rtp + rfp):.2f}" if (rtp + rfp) > 0 else "N/A"
            reg_rec = f"{rtp / (rtp + rfn):.2f}" if (rtp + rfn) > 0 else "N/A"

            if i_pos:
                validated_accuracy = (
                    f"Independent E3.4 empirical measurement (small-N={len(i_pos)}, P={ind_prec}, R={ind_rec})"
                )
            elif r_pos:
                validated_accuracy = (
                    f"Regression-only measurement (N={len(r_pos)}, P={reg_prec}, R={reg_rec}; not independent)"
                )
            else:
                validated_accuracy = "Unvalidated (0 positive evaluation instances)"

            # Overall non-inflated classification
            if in_enterprise_direct and unit_pair is not None:
                classification = "Production direct extraction (unit-tested & E3.4 independent small-N)"
            elif has_ob_kw and i_pos and itp > 0:
                classification = "Production deterministic keyword/bridge rule (E3.4 independent small-N measured)"
            elif has_ob_kw and (unit_pair is not None or (r_pos and rtp > 0)):
                classification = "Production deterministic keyword/bridge rule (tested on regression/unit fixtures only)"
            elif has_ob_kw:
                classification = "Implemented keyword mapping only (unvalidated / semantic candidate support)"
            else:
                classification = "Experimental EngineA1 only (not wired into production policy.py clause extraction)"

            impl_counts[implemented_capability] = impl_counts.get(implemented_capability, 0) + 1
            test_counts[tested_capability] = test_counts.get(tested_capability, 0) + 1
            val_bucket = validated_accuracy.split(" (")[0]
            val_counts[val_bucket] = val_counts.get(val_bucket, 0) + 1
            class_counts[classification] = class_counts.get(classification, 0) + 1

            direct_support = []
            if in_enterprise_direct:
                direct_support.append("policy.py:ENTERPRISE_FACET_PATTERNS")
            elif in_generic_external_only:
                direct_support.append("policy.py:GENERIC_FACET_PATTERNS(external_only)")
            if has_ob_kw:
                direct_support.append(f"reconciliation.py:facet_keywords({len(kws)})")
            if in_a1_direct:
                direct_support.append("engine_a1.py:regex_pattern(experimental)")

            pos_combined = []
            if unit_pair:
                pos_combined.append(unit_pair[0])
            pos_combined.extend(i_pos[:3])
            pos_combined.extend(r_pos[:3])

            neg_combined = []
            if unit_pair:
                neg_combined.append(unit_pair[1])
            if reg_neg_fp_ids.get(facet):
                neg_combined.extend([f"FP:{x}" for x in reg_neg_fp_ids[facet][:2]])

            rows.append(
                {
                    "facet_id": facet,
                    "parent_control": ctrl_id,
                    "governance_domain": domain,
                    "high_risk_priority": "yes" if domain in HIGH_RISK_DOMAINS else "no",
                    "associated_obligations": ";".join(obs) if obs else "ENTERPRISE_CONTROL_ONLY",
                    "direct_pattern_support": ";".join(direct_support) if direct_support else "none",
                    "generic_bridge_support": ";".join(all_bridges) if all_bridges else "none",
                    "semantic_retrieval_support": (
                        "embedding_plus_llm_stage_b_and_obligation_keywords"
                        if obs
                        else "control_level_embedding_only"
                    ),
                    "supporting_evidence_requirement": ev_reqs,
                    "negation_condition_handling": (
                        "Clause-level ABSENCE_OF_CONTROL_PATTERN + PERMISSIVE_CONTROL_OMISSION_PATTERN + "
                        "protective_prohibition preservation (note: sub-clause optionality not yet isolated per facet)"
                    ),
                    "implemented_capability": implemented_capability,
                    "tested_capability": tested_capability,
                    "validated_accuracy": validated_accuracy,
                    "tested_positive_examples": ";".join(pos_combined) if pos_combined else "none",
                    "tested_negative_examples": ";".join(neg_combined) if neg_combined else "none_facet_specific",
                    "empirical_precision": ind_prec if i_pos else reg_prec,
                    "empirical_recall": ind_rec if i_pos else reg_rec,
                    "independent_e34_tp_fp_fn": f"{itp}/{ifp}/{ifn}" if i_pos else "0/0/0",
                    "regression_p1_tp_fp_fn": f"{rtp}/{rfp}/{rfn}" if r_pos else "0/0/0",
                    "uncertain_or_unsupported_extraction": (
                        "Not wired into production policy.py clause extractor (only experimental EngineA1)"
                        if not in_enterprise_direct and not has_ob_kw
                        else (
                            "Zero positive independent test instances; keyword mapping unvalidated"
                            if not i_pos
                            else "Small-N independent sample; sub-clause optionality/paraphrase requires human review"
                        )
                    ),
                    "classification": classification,
                }
            )

    out_csv = output_path or (REPO_ROOT / "E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv")
    fieldnames = [
        "facet_id",
        "parent_control",
        "governance_domain",
        "high_risk_priority",
        "associated_obligations",
        "direct_pattern_support",
        "generic_bridge_support",
        "semantic_retrieval_support",
        "supporting_evidence_requirement",
        "negation_condition_handling",
        "implemented_capability",
        "tested_capability",
        "validated_accuracy",
        "tested_positive_examples",
        "tested_negative_examples",
        "empirical_precision",
        "empirical_recall",
        "independent_e34_tp_fp_fn",
        "regression_p1_tp_fp_fn",
        "uncertain_or_unsupported_extraction",
        "classification",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "total_facets": len(rows),
        "high_risk_facets": sum(1 for r in rows if r["high_risk_priority"] == "yes"),
        "implemented_capability_counts": impl_counts,
        "tested_capability_counts": test_counts,
        "validated_accuracy_counts": val_counts,
        "classification_counts": class_counts,
    }


if __name__ == "__main__":
    out_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    summary = build_facet_coverage_matrix(out_arg)
    print(json.dumps(summary, indent=2))
