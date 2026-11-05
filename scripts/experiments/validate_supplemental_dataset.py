"""Validation script for P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json.

Ensures structural integrity, contrastive pair balance, taxonomy compliance,
and strictly verifies zero leakage into the P1_EVALUATION_DATASET_V2.json holdout set.
"""

from __future__ import annotations

import json
from pathlib import Path


def tokenize(text: str) -> set[str]:
    stopwords = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "is", "are", "from", "by", "that", "all"}
    raw_tokens = [t.strip(".,;:\"'()[]{}") for t in text.lower().split()]
    return {t for t in raw_tokens if len(t) > 2 and t not in stopwords}


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def validate_dataset():
    repo_root = Path(__file__).resolve().parent.parent.parent
    supp_path = repo_root / "P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json"
    v2_path = repo_root / "P1_EVALUATION_DATASET_V2.json"
    ucl_path = repo_root / "UNIFIED_CONTROL_LIBRARY.json"

    assert supp_path.exists(), f"Missing {supp_path}"
    assert v2_path.exists(), f"Missing {v2_path}"
    assert ucl_path.exists(), f"Missing {ucl_path}"

    with open(supp_path, "r", encoding="utf-8") as f:
        supp_data = json.load(f)

    with open(v2_path, "r", encoding="utf-8") as f:
        v2_data = json.load(f)

    with open(ucl_path, "r", encoding="utf-8") as f:
        ucl_data = json.load(f)

    cases = supp_data.get("cases", [])
    print(f"Validating {len(cases)} cases in P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json...")

    # 1. Total count
    assert len(cases) >= 30, f"Expected at least 30 cases, found {len(cases)}"
    assert len(cases) == 36, f"Expected exactly 36 cases, found {len(cases)}"

    # 2. Taxonomy validity
    canonical_controls = {c["control_id"] for c in ucl_data["controls"]}
    canonical_facets = {f for c in ucl_data["controls"] for f in c.get("control_facets", [])}

    for case in cases:
        for ctrl in case.get("expected_controls", []):
            assert ctrl in canonical_controls, f"Invalid canonical control '{ctrl}' in case {case['case_id']}"
        for facet in case.get("expected_facets", []):
            assert facet in canonical_facets, f"Invalid canonical facet '{facet}' in case {case['case_id']}"

    # 3. Normative class coverage
    expected_norm_classes = {
        "affirmative_obligation",
        "prohibition_absolute",
        "prohibition_conditional",
        "scope_exemption",
        "permissive_guidance",
        "aspirational_statement",
    }
    actual_norm_classes = {c["normative_type"] for c in cases}
    missing_classes = expected_norm_classes - actual_norm_classes
    assert not missing_classes, f"Missing normative classes: {missing_classes}"

    # 4. Candidate behavior balance
    n_should = sum(1 for c in cases if c["expected_candidate_behavior"] == "should_generate_candidates")
    n_must_not = sum(1 for c in cases if c["expected_candidate_behavior"] == "must_not_generate_candidates")
    print(f"  Candidate Generation Balance: {n_should} affirmative vs {n_must_not} suppressed")
    assert n_should == 18, f"Expected 18 should_generate_candidates, got {n_should}"
    assert n_must_not == 18, f"Expected 18 must_not_generate_candidates, got {n_must_not}"

    # 5. Contrastive pairs
    pairs = {}
    for c in cases:
        pid = c.get("pair_id")
        assert pid, f"Case {c['case_id']} missing pair_id"
        pairs.setdefault(pid, []).append(c)

    assert len(pairs) == 18, f"Expected 18 contrastive pairs, got {len(pairs)}"
    for pid, pair_cases in pairs.items():
        assert len(pair_cases) == 2, f"Pair {pid} does not have exactly 2 cases"
        behaviors = {c["expected_candidate_behavior"] for c in pair_cases}
        assert behaviors == {"should_generate_candidates", "must_not_generate_candidates"}, (
            f"Pair {pid} must contain 1 affirmative and 1 suppressed case, got {behaviors}"
        )

    # 6. Leakage Check against V2 Holdout Split
    holdout_cases = [c for c in v2_data["cases"] if c.get("split") == "holdout"]
    assert len(holdout_cases) == 51, f"Expected 51 holdout cases, got {len(holdout_cases)}"

    print("  Checking for leakage against 51 frozen holdout cases...")
    max_sim = 0.0
    highest_pair = None

    for supp_c in cases:
        supp_text = supp_c["input_text"]
        supp_tokens = tokenize(supp_text)

        for hold_c in holdout_cases:
            hold_text = hold_c["input_text"]
            # Exact match check
            assert supp_text.lower() != hold_text.lower(), (
                f"LEAKAGE: Exact string match found between {supp_c['case_id']} and holdout {hold_c['case_id']}"
            )

            # Jaccard overlap check
            hold_tokens = tokenize(hold_text)
            sim = jaccard_similarity(supp_tokens, hold_tokens)
            if sim > max_sim:
                max_sim = sim
                highest_pair = (supp_c["case_id"], hold_c["case_id"], sim)

            assert sim < 0.65, (
                f"LEAKAGE: Excessive token overlap ({sim:.2f}) between {supp_c['case_id']} and holdout {hold_c['case_id']}"
            )

    print(f"  Maximum holdout Jaccard similarity: {max_sim:.3f} (Pair: {highest_pair[0]} vs {highest_pair[1]})")
    print("SUCCESS: Supplemental Adversarial Dataset validation PASSED with ZERO leakage!")


if __name__ == "__main__":
    validate_dataset()
