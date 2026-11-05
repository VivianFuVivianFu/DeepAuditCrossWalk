"""Validation harness for P1_EVALUATION_DATASET_V2.json.

Ensures schema integrity, taxonomic consistency with UNIFIED_CONTROL_LIBRARY.json,
strict partition between development and holdout splits, and truthful provenance reporting.
"""

import json
import sys
from pathlib import Path

def validate_dataset():
    repo_root = Path(__file__).resolve().parent.parent
    dataset_path = repo_root / "P1_EVALUATION_DATASET_V2.json"
    ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"

    if not dataset_path.exists():
        print(f"FAIL: {dataset_path} does not exist.")
        sys.exit(1)

    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)

    with open(ucl_path, encoding="utf-8") as f:
        ucl = json.load(f)

    valid_controls = {c["control_id"] for c in ucl["controls"]}
    valid_facets = {f for c in ucl["controls"] for f in c["control_facets"]}

    cases = data.get("cases", [])
    print(f"Validating {len(cases)} cases in {data.get('dataset_id')} (v{data.get('version')})...")

    if len(cases) < 150:
        print(f"FAIL: Dataset must contain at least 150 cases, found {len(cases)}")
        sys.exit(1)

    case_ids = set()
    dev_texts = set()
    holdout_texts = set()

    dev_count = 0
    holdout_count = 0
    ambiguous_count = 0

    required_fields = {
        "case_id", "split", "source_type", "category", "input_text",
        "expected_atomic_requirements", "expected_facets", "expected_controls",
        "applicability_conditions", "expected_review_status",
        "ground_truth_provenance", "reviewer_status", "label_confidence",
        "normative_type", "expected_candidate_behavior", "original_is_negated"
    }

    valid_normative_types = {
        "mandatory_requirement", "mandatory_prohibition", "conditional_exemption",
        "harmful_practice_prohibition", "applicability_boundary", "unmapped_preference",
        "uncertain_prohibition", "absence_of_control"
    }

    valid_candidate_behaviors = {
        "should_generate_candidates", "must_not_generate_candidates", "undetermined_ambiguity"
    }

    errors = []

    for idx, c in enumerate(cases):
        cid = c.get("case_id", f"INDEX-{idx}")
        if cid in case_ids:
            errors.append(f"Duplicate case_id: {cid}")
        case_ids.add(cid)

        # Schema fields check
        missing = required_fields - set(c.keys())
        if missing:
            errors.append(f"Case {cid} missing fields: {missing}")

        split = c.get("split")
        if split == "development":
            dev_count += 1
            dev_texts.add(c.get("input_text", "").strip().lower())
        elif split == "holdout":
            holdout_count += 1
            holdout_texts.add(c.get("input_text", "").strip().lower())
        else:
            errors.append(f"Case {cid} invalid split '{split}'")

        # Canonical UCL validation
        for ctrl in c.get("expected_controls", []):
            if ctrl not in valid_controls:
                errors.append(f"Case {cid} has unknown control ID '{ctrl}'")
        for facet in c.get("expected_facets", []):
            if facet not in valid_facets:
                errors.append(f"Case {cid} has unknown facet name '{facet}'")

        # P1B-0 Negation Semantics Validation
        nt = c.get("normative_type")
        if nt not in valid_normative_types:
            errors.append(f"Case {cid} invalid normative_type '{nt}'")
        cb = c.get("expected_candidate_behavior")
        if cb not in valid_candidate_behaviors:
            errors.append(f"Case {cid} invalid expected_candidate_behavior '{cb}'")

        if cid in {"P1-127", "P1-155"}:
            if cb != "must_not_generate_candidates" or len(c.get("expected_controls", [])) > 0:
                errors.append(f"Case {cid} must have expected_candidate_behavior='must_not_generate_candidates' and expected_controls=[]")
        elif cid in {"P1-027", "P1-049", "P1-072", "P1-090", "P1-108", "P1-139", "P1-148", "P1-154"}:
            if nt != "mandatory_prohibition" or cb != "should_generate_candidates":
                errors.append(f"Case {cid} must have normative_type='mandatory_prohibition' and expected_candidate_behavior='should_generate_candidates'")

        if c.get("ground_truth_provenance") == "ambiguous_legal":
            ambiguous_count += 1

        # Check truthful provenance
        if c.get("reviewer_status") == "panel_verified":
            errors.append(f"Case {cid} falsely claims 'panel_verified' prior to independent expert review")

    # Check for split leakage
    overlap = dev_texts & holdout_texts
    if overlap:
        errors.append(f"Data leakage detected! {len(overlap)} text(s) present in both development and holdout splits: {list(overlap)[:3]}")

    # Summary reporting
    print(f"Validation Summary:")
    print(f"  Total Cases:       {len(cases)}")
    print(f"  Development Split: {dev_count} ({dev_count/len(cases)*100:.1f}%)")
    print(f"  Holdout Split:     {holdout_count} ({holdout_count/len(cases)*100:.1f}%)")
    print(f"  Ambiguous Legal:   {ambiguous_count}")
    print(f"  Leakage Overlap:   {len(overlap)}")

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for e in errors[:10]:
            print(f"  - {e}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more.")
        sys.exit(1)

    print("\nSUCCESS: All P1_EVALUATION_DATASET_V2.json integrity checks PASSED!")

if __name__ == "__main__":
    validate_dataset()
