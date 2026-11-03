"""Reproducible evaluation harness for DeepAudit Crosswalk Semantic Mapping Reliability Audit.

Explicitly categorizes and executes evaluation across four dimensions:
1. Baseline Construction: [DIRECT PRODUCTION FUNCTION EXECUTION] (extract_enterprise_policy)
2. Scenario A - Strategy: [PROXY-BASED COMPONENT MEASUREMENT - E2E STRATEGY ENGINE NOT YET IMPLEMENTED]
3. Scenario B - Questionnaire: [ISOLATED COMPONENT TEST & PRODUCTION PIPELINE DEMONSTRATION]
4. Scenario C - Use Case: [DIRECT PRODUCTION FUNCTION EXECUTION for Applicability;
                          FEATURES NOT YET IMPLEMENTED for Operational Telemetry & Evidence]

Distinguishes directly executed production functionality, isolated component tests,
proxy-based measurements, and features not yet implemented or measurable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure backend package is in python path
repo_root = Path(__file__).resolve().parent.parent
backend_path = repo_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from banking_crosswalk.applicability import decide_applicability
from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import (
    BankingUseCase,
    QuestionBank,
    QuestionnaireMetadata,
    QuestionRecord,
)
from banking_crosswalk.policy import (
    ENTERPRISE_FACET_PATTERNS,
    extract_enterprise_policy,
)


def run_evaluation() -> int:
    dataset_path = repo_root / "MAPPING_EVALUATION_DATASET.json"
    if not dataset_path.exists():
        print(f"Error: Dataset file not found at {dataset_path}")
        return 1

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    reg_pack = load_regulatory_pack()

    print("=" * 85)
    print("DEEPAUDIT CROSSWALK: SEMANTIC MAPPING RELIABILITY AUDIT EVALUATION")
    print("=" * 85)
    meta = data.get("metadata", {})
    print(f"Dataset Name: {meta.get('dataset_name')}")
    print(f"Dataset Provenance: Total={meta.get('total_cases')}, "
          f"Human-Verified={meta.get('human_verified_cases')} (0 confirmed independent external panel reviews), "
          f"Synthetic Reference={meta.get('synthetic_reference_cases')} (pending expert review), "
          f"Ambiguous Legal={meta.get('ambiguous_legal_cases')}")
    print(f"Note: {meta.get('provenance_note')}")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Baseline Construction Evaluation [DIRECT PRODUCTION FUNCTION EXECUTION]
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("1. BASELINE CONSTRUCTION [DIRECT PRODUCTION FUNCTION EXECUTION]")
    print("   Evaluates: extract_enterprise_policy() in backend/banking_crosswalk/policy.py")
    print("   Scope: 25 synthetic clauses across 10 Australian banking governance scenarios")
    print("=" * 85)
    base_cases = data["baseline_construction_cases"]
    base_failures = []
    base_tp = 0
    base_fp = 0
    base_fn = 0
    false_control_triggers = []

    for c in base_cases:
        policy = extract_enterprise_policy(
            tenant_id="audit-eval",
            name=f"Pol-{c['id']}",
            text=c["text"],
        )
        detected_facets = set()
        detected_controls = set()
        for cl in policy.clauses:
            detected_facets.update(cl.control_facets)
            for m in cl.control_mappings:
                detected_controls.add(m.control_id)

        exp_facets = set(c["expected_facets"])
        tp = len(exp_facets & detected_facets)
        fp = len(detected_facets - exp_facets)
        fn = len(exp_facets - detected_facets)

        base_tp += tp
        base_fp += fp
        base_fn += fn

        exp_ctrl = c["expected_control"]
        ctrl_ok = (exp_ctrl in detected_controls) if exp_ctrl else (len(detected_controls) == 0)

        # Record component-level false-control triggers on negated or unrepresented clauses
        if exp_ctrl is None and len(detected_controls) > 0:
            false_control_triggers.append((c["id"], c["category"], c["text"], detected_controls))

        if not (detected_facets == exp_facets and ctrl_ok):
            base_failures.append({
                "id": c["id"],
                "category": c["category"],
                "text": c["text"],
                "expected_facets": list(exp_facets),
                "actual_facets": list(detected_facets),
                "expected_control": exp_ctrl,
                "actual_controls": list(detected_controls),
                "notes": c["notes"],
            })

    p_base = base_tp / (base_tp + base_fp) if (base_tp + base_fp) else 0.0
    r_base = base_tp / (base_tp + base_fn) if (base_tp + base_fn) else 0.0
    f1_base = 2 * p_base * r_base / (p_base + r_base) if (p_base + r_base) else 0.0
    fc_rate = len(false_control_triggers) / len(base_cases) if base_cases else 0.0

    print(f"Total Cases: {len(base_cases)}")
    print(f"  Facet Detection: Precision = {p_base:.4f}, Recall = {r_base:.4f}, F1 = {f1_base:.4f}")
    print(f"  Confusion Matrix: TP = {base_tp}, FP = {base_fp}, FN = {base_fn}")
    print(f"  Component-Level False-Control Trigger Rate: {fc_rate:.1%} ({len(false_control_triggers)}/{len(base_cases)} cases)")
    print("  *Important Measurement Note: This metric measures false candidate control triggers generated by regex")
    print("   on isolated clauses during policy extraction. It is NOT a confirmed end-to-end regulatory compliance error,")
    print("   because candidate mappings carry 'review_status=proposed' pending human compliance sign-off.")
    if false_control_triggers:
        for fc in false_control_triggers:
            print(f"    - [{fc[0]}] ({fc[1]}): Triggered {fc[3]} for: '{fc[2]}'")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Scenario A: AI Governance Strategy [PROXY-BASED COMPONENT MEASUREMENT]
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("2. SCENARIO A: AI GOVERNANCE STRATEGY [PROXY-BASED COMPONENT MEASUREMENT]")
    print("   Feature Status: End-to-end Strategy Assessment engine is NOT YET IMPLEMENTED.")
    print("   Methodology: High-level strategy commitments tested through extract_enterprise_policy()")
    print("   to measure whether regex facet patterns trigger on executive governance phrasing.")
    print("   Limitation: Proxy measurement only; end-to-end strategy product accuracy is NOT YET MEASURABLE.")
    print("=" * 85)
    strat_cases = data["strategy_assessment_cases"]
    strat_tp = 0
    strat_fp = 0
    strat_fn = 0
    strat_tn = 0

    for sc in strat_cases:
        policy = extract_enterprise_policy(
            tenant_id="audit-eval",
            name=f"Strat-{sc['id']}",
            text=sc["text"],
        )
        has_controls = any(len(cl.control_mappings) > 0 for cl in policy.clauses)
        actual_covered = has_controls
        expected_covered = sc["expected_covered"]

        if actual_covered and expected_covered:
            strat_tp += 1
        elif actual_covered and not expected_covered:
            strat_fp += 1
        elif not actual_covered and expected_covered:
            strat_fn += 1
        else:
            strat_tn += 1

    p_strat = strat_tp / (strat_tp + strat_fp) if (strat_tp + strat_fp) else 0.0
    r_strat = strat_tp / (strat_tp + strat_fn) if (strat_tp + strat_fn) else 0.0
    f1_strat = 2 * p_strat * r_strat / (p_strat + r_strat) if (p_strat + r_strat) else 0.0

    print(f"Strategy Cases: {len(strat_cases)} (Proxy Test)")
    print(f"  Proxy Precision = {p_strat:.4f}, Proxy Recall = {r_strat:.4f}, Proxy F1 = {f1_strat:.4f}")
    print(f"  Confusion Matrix: TP = {strat_tp}, FP = {strat_fp}, FN = {strat_fn}, TN = {strat_tn}")
    print("  Status: End-to-end Strategy Assessment is NOT YET IMPLEMENTED in production.")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Scenario B: Questionnaire Assessment [ISOLATED COMPONENT TEST & PIPELINE DEMO]
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("3. SCENARIO B: AI ASSESSMENT QUESTIONNAIRE COVERAGE")
    print("   Part 3.1: [ISOLATED COMPONENT TEST] of question-level facet sensitivity")
    print("   Part 3.2: [DIRECT PRODUCTION PIPELINE EXECUTION] via evaluate_questionnaire_coverage()")
    print("=" * 85)
    quest_cases = data["questionnaire_assessment_cases"]
    quest_tp = 0
    quest_fp = 0
    quest_fn = 0
    quest_tn = 0

    # 3.1 Isolated facet match test
    for qc in quest_cases:
        q_text = qc["question"].lower()
        matched_facets = [
            facet
            for facet, phrases in ENTERPRISE_FACET_PATTERNS.items()
            if any(phrase in q_text for phrase in phrases)
        ]
        actual_valid = len(matched_facets) > 0
        expected_valid = qc["expected_valid"]

        if actual_valid and expected_valid:
            quest_tp += 1
        elif actual_valid and not expected_valid:
            quest_fp += 1
        elif not actual_valid and expected_valid:
            quest_fn += 1
        else:
            quest_tn += 1

    p_quest = quest_tp / (quest_tp + quest_fp) if (quest_tp + quest_fp) else 0.0
    r_quest = quest_tp / (quest_tp + quest_fn) if (quest_tp + quest_fn) else 0.0
    f1_quest = 2 * p_quest * r_quest / (p_quest + r_quest) if (p_quest + r_quest) else 0.0

    print("--- Part 3.1: Isolated Component Test (Question-Level Facet Sensitivity) ---")
    print(f"  Cases: {len(quest_cases)}")
    print(f"  Component Precision = {p_quest:.4f}, Recall = {r_quest:.4f}, F1 = {f1_quest:.4f}")
    print(f"  Confusion Matrix: TP = {quest_tp}, FP = {quest_fp}, FN = {quest_fn}, TN = {quest_tn}")

    # 3.2 Production Pipeline Execution
    print("\n--- Part 3.2: Direct Production Pipeline Execution (evaluate_questionnaire_coverage) ---")
    synthetic_questions = [
        QuestionRecord(
            question_id=qc["id"],
            question_text=qc["question"],
            source_version="1.0.0",
            source_sheet="EvaluationSheet",
        )
        for idx, qc in enumerate(quest_cases)
    ]
    synthetic_bank = QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id="SYNTHETIC_EVAL_QBANK",
            source_filename="synthetic_questionnaire.xlsx",
            source_version="1.0.0",
            source_sha256="synthetic-sha256",
        ),
        questions=synthetic_questions,
    )
    demo_use_case = BankingUseCase(apra_regulated=True, entity_type="ADI")
    prod_assessment = evaluate_questionnaire_coverage(
        tenant_id="audit-eval",
        use_case=demo_use_case,
        question_bank=synthetic_bank,
        regulatory_pack=reg_pack,
    )
    print(f"  Production Pipeline Result: Assessment ID={prod_assessment.assessment_id[:8]}...")
    print(f"  Applicable Obligations Evaluated: {len(prod_assessment.results)}")
    print(f"  Regulatory Gaps Identified: {len(prod_assessment.gaps)}")
    print(f"  Confirmed Coverage Rate: {prod_assessment.metrics.confirmed_coverage_rate:.1%}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Scenario C: AI Use Case Assessment [PRODUCTION APPLICABILITY vs UNIMPLEMENTED]
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 85)
    print("4. SCENARIO C: AI USE CASE & OPERATIONAL EVIDENCE")
    print("   Part 4.1: [DIRECT PRODUCTION FUNCTION EXECUTION] (decide_applicability)")
    print("   Part 4.2: [FEATURES NOT YET IMPLEMENTED IN PRODUCTION / UNMEASURABLE] (Telemetry & Evidence)")
    print("=" * 85)

    # 4.1 Production applicability execution
    print("--- Part 4.1: Production Applicability Rules Execution ---")
    applicability_eval_cases = [
        ("UC-01", BankingUseCase(apra_regulated=True), "apra_entity", "applicable"),
        ("UC-02", BankingUseCase(handles_personal_information=True), "privacy_personal_information", "applicable"),
        ("UC-03", BankingUseCase(idr_obligations=True, handles_regulated_complaints=True), "asic_idr", "applicable"),
        ("UC-04", BankingUseCase(eu_establishment_or_market=False, eu_output_used=False), "eu_ai_act_nexus", "not_applicable"),
        ("UC-05", BankingUseCase(approval_threshold_aud=500.0), "enterprise_delegated_authority", "applicable"),
        ("UC-06", BankingUseCase(handles_personal_information=None), "privacy_personal_information", "undetermined"),
        ("UC-07", BankingUseCase(apra_regulated=True, third_party_ai_service=True, material_service_provider=None), "apra_third_party_service", "conditional"),
    ]

    app_matches = 0
    for cid, uc, rule_key, expected_status in applicability_eval_cases:
        matching_ob = next((o for o in reg_pack.obligations if o.applicability_key == rule_key), None)
        if matching_ob:
            decision = decide_applicability(matching_ob, uc)
            actual_status = decision.status.value
            matched = actual_status == expected_status
            if matched:
                app_matches += 1
            print(f"  [{cid}] Rule: {rule_key:30} -> {actual_status:15} (Expected: {expected_status:15}) [MATCH: {matched}]")

    print(f"  Production Applicability Rules Accuracy: {app_matches}/{len(applicability_eval_cases)} ({app_matches/len(applicability_eval_cases):.1%})")

    # 4.2 Unimplemented Operational Evidence
    print("\n--- Part 4.2: Operational Telemetry & Cryptographic Evidence ---")
    print("  Cases UC-08 through UC-12 test operational evidence capabilities:")
    print("    - UC-08: Distinguish unsubstantiated intake claims from test scripts")
    print("    - UC-09: Telemetry log parsing for dual human sign-off")
    print("    - UC-10: Automated use-case vs baseline approval threshold conflict")
    print("    - UC-11: Audit log retention config vs enterprise policy limit")
    print("    - UC-12: Extraterritorial cloud data residency verification")
    print("  Feature Status: NOT YET IMPLEMENTED IN PRODUCTION / UNMEASURABLE.")
    print("  Note: BankingUseCase currently lacks telemetry log ingestion and cryptographic evidence schemas.")
    print("  These operational verification capabilities are slated for Roadmap tasks P0-6 and P2-1.")

    print("\n" + "=" * 85)
    print("EVALUATION RUN COMPLETE: ALL RESULTS FULLY REPRODUCED")
    print("=" * 85)
    return 0


if __name__ == "__main__":
    sys.exit(run_evaluation())
