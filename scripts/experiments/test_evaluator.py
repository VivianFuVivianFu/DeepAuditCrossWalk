"""Unit tests for the shared evaluation harness and scoring logic."""

from scripts.experiments.evaluator import compute_aggregate_metrics, evaluate_case
from scripts.experiments.models import (
    CandidatePrediction,
    ExtractionResult,
    ThresholdAST,
)


def test_evaluate_case_affirmative_match():
    case = {
        "case_id": "TEST-01",
        "split": "development",
        "category": "exact_match",
        "normative_type": "mandatory_requirement",
        "expected_candidate_behavior": "should_generate_candidates",
        "input_text": "All credit decisions over AUD $500,000 must obtain dual sign-off.",
        "expected_atomic_requirements": ["Obtain dual sign-off for credit over $500,000"],
        "expected_facets": ["approval_threshold_defined", "human_approval_required"],
        "expected_controls": ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
        "threshold_constraint": {"amount": 500000.0, "operator": ">"},
    }

    prediction = ExtractionResult(
        case_id="TEST-01",
        extracted_clauses=["All credit decisions over AUD $500,000 must obtain dual sign-off."],
        candidate_facets=["approval_threshold_defined", "human_approval_required"],
        candidate_controls=["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
        ranked_mappings=[
            CandidatePrediction(
                clause_id="POL-1",
                canonical_control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
                canonical_facet_id="approval_threshold_defined",
                score=1.0,
                review_status="proposed",
            )
        ],
        threshold_ast=ThresholdAST(amount=500000.0, operator=">", currency="AUD"),
    )

    res = evaluate_case(prediction, case)
    assert res.facet_tp == 2
    assert res.facet_fp == 0
    assert res.facet_fn == 0
    assert res.top1_match is True
    assert res.top3_match is True
    assert res.reciprocal_rank == 1.0
    assert res.false_control_trigger is False
    assert res.threshold_correct is True


def test_evaluate_case_prohibition_suppression():
    """Test that a must_not_generate_candidates case correctly suppresses candidate generation."""
    case = {
        "case_id": "TEST-SUPPRESS-01",
        "split": "development",
        "category": "prohibition",
        "normative_type": "prohibition_absolute",
        "expected_candidate_behavior": "must_not_generate_candidates",
        "input_text": "Employees must not store unencrypted customer passwords under any circumstances.",
        "expected_atomic_requirements": [],
        "expected_facets": [],
        "expected_controls": [],
    }

    # Case 1: Engine correctly suppresses
    pred_suppressed = ExtractionResult(
        case_id="TEST-SUPPRESS-01",
        extracted_clauses=[case["input_text"]],
        candidate_facets=[],
        candidate_controls=[],
        ranked_mappings=[],
        is_suppressed=True,
    )
    res1 = evaluate_case(pred_suppressed, case)
    assert res1.false_control_trigger is False
    assert res1.correct_suppression is True

    # Case 2: Engine fails and generates candidates (false trigger)
    pred_failed = ExtractionResult(
        case_id="TEST-SUPPRESS-01",
        extracted_clauses=[case["input_text"]],
        candidate_facets=["security_controls_defined"],
        candidate_controls=["CTRL-PRIV-SECURITY-RETENTION"],
        ranked_mappings=[
            CandidatePrediction(
                clause_id="POL-2",
                canonical_control_id="CTRL-PRIV-SECURITY-RETENTION",
                review_status="proposed",
            )
        ],
        is_suppressed=False,
    )
    res2 = evaluate_case(pred_failed, case)
    assert res2.false_control_trigger is True
    assert res2.correct_suppression is False


def test_compute_aggregate_metrics():
    # Construct 2 mock case results
    case1 = {
        "case_id": "C1",
        "split": "development",
        "category": "exact",
        "normative_type": "mandatory_requirement",
        "expected_candidate_behavior": "should_generate_candidates",
        "input_text": "Short requirement text.",
        "expected_controls": ["CTRL-SEC-INCIDENT"],
        "expected_facets": ["incident_detection_defined"],
    }
    pred1 = ExtractionResult(
        case_id="C1",
        candidate_facets=["incident_detection_defined"],
        candidate_controls=["CTRL-SEC-INCIDENT"],
        ranked_mappings=[
            CandidatePrediction(
                clause_id="P1",
                canonical_control_id="CTRL-SEC-INCIDENT",
                review_status="proposed",
            )
        ],
    )
    res1 = evaluate_case(pred1, case1)

    case2 = {
        "case_id": "C2",
        "split": "development",
        "category": "prohibition",
        "normative_type": "prohibition_absolute",
        "expected_candidate_behavior": "must_not_generate_candidates",
        "input_text": "Prohibited practice statement.",
        "expected_controls": [],
        "expected_facets": [],
    }
    pred2 = ExtractionResult(
        case_id="C2",
        candidate_facets=[],
        candidate_controls=[],
        ranked_mappings=[],
        is_suppressed=True,
    )
    res2 = evaluate_case(pred2, case2)

    metrics = compute_aggregate_metrics([res1, res2])
    assert metrics["total_cases"] == 2
    assert metrics["layer_b_facets"]["f1_micro"] == 1.0
    assert metrics["layer_c_controls"]["top1_recall"] == 1.0
    assert metrics["layer_c_normative_safety"]["suppression_accuracy"] == 1.0
    assert metrics["layer_c_normative_safety"]["false_trigger_rate"] == 0.0
