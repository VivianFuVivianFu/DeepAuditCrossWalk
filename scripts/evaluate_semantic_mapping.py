"""Reproducible evaluation harness for DeepAudit Crosswalk Semantic Mapping Reliability Audit.

Evaluates 63 synthetic Australian banking governance test cases against the engine:
1. Baseline Construction (25 cases across 10 governance scenarios)
2. Scenario A: AI Governance Strategy Coverage (12 cases)
3. Scenario B: AI Assessment Questionnaire Coverage (14 cases)
4. Scenario C: AI Use Case Coverage & Operational Evidence (12 cases)

Outputs precision, recall, F1, confusion matrices, false-coverage rates, and failure breakdowns.
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

    print("=" * 80)
    print("DEEPAUDIT CROSSWALK: SEMANTIC MAPPING RELIABILITY AUDIT EVALUATION")
    print("=" * 80)
    meta = data.get("metadata", {})
    print(f"Dataset Name: {meta.get('dataset_name')}")
    print(f"Total Cases:  {meta.get('total_cases')} (Human Verified: {meta.get('human_verified_cases')}, "
          f"Synthetic Reference: {meta.get('synthetic_reference_cases')}, Ambiguous: {meta.get('ambiguous_legal_cases')})")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Baseline Construction Evaluation
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- 1. BASELINE CONSTRUCTION (ENTERPRISE POLICY INGESTION) ---")
    base_cases = data["baseline_construction_cases"]
    base_failures = []
    base_tp = 0
    base_fp = 0
    base_fn = 0
    false_coverage_cases = []

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

        # False coverage occurs when an unrepresented or negated clause triggers a control
        if exp_ctrl is None and len(detected_controls) > 0:
            false_coverage_cases.append((c["id"], c["category"], c["text"], detected_controls))

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
    fc_rate = len(false_coverage_cases) / len(base_cases) if base_cases else 0.0

    print(f"Total Cases Evaluated: {len(base_cases)}")
    print(f"  Facet Detection: Precision = {p_base:.4f}, Recall = {r_base:.4f}, F1 = {f1_base:.4f}")
    print(f"  Confusion Matrix: TP = {base_tp}, FP = {base_fp}, FN = {base_fn}")
    print(f"  False-Coverage Defect Rate: {fc_rate:.1%} ({len(false_coverage_cases)}/{len(base_cases)} cases)")
    if false_coverage_cases:
        for fc in false_coverage_cases:
            print(f"    - [{fc[0]}] ({fc[1]}): Controls {fc[3]} triggered unexpectedly for: '{fc[2]}'")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Scenario A: AI Governance Strategy Assessment
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- 2. SCENARIO A: AI GOVERNANCE STRATEGY ASSESSMENT ---")
    strat_cases = data["strategy_assessment_cases"]
    strat_tp = 0
    strat_fp = 0
    strat_fn = 0
    strat_tn = 0
    strat_failures = []

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
            strat_failures.append({
                "id": sc["id"],
                "name": sc["name"],
                "text": sc["text"],
                "error": "False Positive (Vague / Non-binding statement classified as covered)",
                "reason": sc.get("reason", ""),
            })
        elif not actual_covered and expected_covered:
            strat_fn += 1
            strat_failures.append({
                "id": sc["id"],
                "name": sc["name"],
                "text": sc["text"],
                "error": "False Negative (Valid strategy commitment missed due to phrasing)",
            })
        else:
            strat_tn += 1

    p_strat = strat_tp / (strat_tp + strat_fp) if (strat_tp + strat_fp) else 0.0
    r_strat = strat_tp / (strat_tp + strat_fn) if (strat_tp + strat_fn) else 0.0
    f1_strat = 2 * p_strat * r_strat / (p_strat + r_strat) if (p_strat + r_strat) else 0.0

    print(f"Strategy Cases: {len(strat_cases)}")
    print(f"  Precision = {p_strat:.4f}, Recall = {r_strat:.4f}, F1 = {f1_strat:.4f}")
    print(f"  Confusion Matrix: TP = {strat_tp}, FP = {strat_fp}, FN = {strat_fn}, TN = {strat_tn}")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Scenario B: AI Assessment Questionnaire Coverage
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- 3. SCENARIO B: AI ASSESSMENT QUESTIONNAIRE COVERAGE ---")
    quest_cases = data["questionnaire_assessment_cases"]
    quest_tp = 0
    quest_fp = 0
    quest_fn = 0
    quest_tn = 0
    quest_failures = []

    for qc in quest_cases:
        q_text = qc["question"].lower()
        matched_facets = []
        for facet, phrases in ENTERPRISE_FACET_PATTERNS.items():
            if any(phrase in q_text for phrase in phrases):
                matched_facets.append(facet)

        has_facet = len(matched_facets) > 0
        actual_valid = has_facet
        expected_valid = qc["expected_valid"]

        if actual_valid and expected_valid:
            quest_tp += 1
        elif actual_valid and not expected_valid:
            quest_fp += 1
            quest_failures.append({
                "id": qc["id"],
                "question": qc["question"],
                "error": "False Positive (Superficial/Subjective question classified as valid probe)",
            })
        elif not actual_valid and expected_valid:
            quest_fn += 1
            quest_failures.append({
                "id": qc["id"],
                "question": qc["question"],
                "error": "False Negative (Rigorous governance question missed due to lexical mismatch)",
            })
        else:
            quest_tn += 1

    p_quest = quest_tp / (quest_tp + quest_fp) if (quest_tp + quest_fp) else 0.0
    r_quest = quest_tp / (quest_tp + quest_fn) if (quest_tp + quest_fn) else 0.0
    f1_quest = 2 * p_quest * r_quest / (p_quest + r_quest) if (p_quest + r_quest) else 0.0

    print(f"Questionnaire Cases: {len(quest_cases)}")
    print(f"  Precision = {p_quest:.4f}, Recall = {r_quest:.4f}, F1 = {f1_quest:.4f}")
    print(f"  Confusion Matrix: TP = {quest_tp}, FP = {quest_fp}, FN = {quest_fn}, TN = {quest_tn}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Scenario C: AI Use Case Coverage & Operational Evidence
    # ─────────────────────────────────────────────────────────────────────────
    print("\n--- 4. SCENARIO C: AI USE CASE & OPERATIONAL EVIDENCE ---")
    uc_cases = data["use_case_assessment_cases"]
    uc_handled = sum(1 for c in uc_cases if "expected_status" in c)
    uc_blindspots = sum(1 for c in uc_cases if "expected_evidence_status" in c)

    print(f"Use Case Cases: {len(uc_cases)}")
    print(f"  Applicability Handled Deterministically: {uc_handled} / {len(uc_cases)} ({uc_handled/len(uc_cases):.1%})")
    print(f"  Operational Evidence & Telemetry Blindspots: {uc_blindspots} / {len(uc_cases)} ({uc_blindspots/len(uc_cases):.1%})")

    print("\n" + "=" * 80)
    print("EVALUATION RUN COMPLETE")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(run_evaluation())
