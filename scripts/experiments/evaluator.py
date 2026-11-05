"""Unified deterministic evaluation harness for Phase P1B experiments.

Implements scoring across Layers A, B, C, F, and Normative Safety according to
P1B0_REVISED_EVALUATION_CONTRACT.md. Never passes labels or answer keys to engines.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

from .models import CaseEvaluationResult, ExtractionResult


def get_length_tier(text: str) -> str:
    """Classify input text length into standard tiers."""
    length = len(text)
    if length < 100:
        return "short"
    if length <= 300:
        return "medium"
    return "long"


def evaluate_case(
    prediction: ExtractionResult,
    case: dict[str, Any],
) -> CaseEvaluationResult:
    """Evaluate a single prediction against ground truth according to the P1B contract."""
    case_id = case.get("case_id", prediction.case_id)
    split = case.get("split", "unknown")
    category = case.get("category", "unknown")
    normative_type = case.get("normative_type", "unknown")
    expected_behavior = case.get("expected_candidate_behavior", "should_generate_candidates")
    input_text = case.get("input_text", "")
    length_tier = get_length_tier(input_text)

    # 1. Layer A: Atomic Segmentation / Requirement Extraction
    exp_atomic = case.get("expected_atomic_requirements", [])
    extracted_clauses = prediction.extracted_clauses
    atomic_tp = 0
    atomic_fp = 0
    atomic_fn = 0
    if exp_atomic:
        # Measure segment alignment via token intersection
        matched_exp = set()
        matched_ext = set()
        for i, ext in enumerate(extracted_clauses):
            ext_tokens = set(ext.lower().split())
            best_match = None
            best_iou = 0.0
            for j, exp in enumerate(exp_atomic):
                exp_tokens = set(exp.lower().split())
                if not exp_tokens:
                    continue
                iou = len(ext_tokens & exp_tokens) / len(ext_tokens | exp_tokens)
                if iou > best_iou:
                    best_iou = iou
                    best_match = j
            if best_iou >= 0.25 and best_match is not None:
                matched_exp.add(best_match)
                matched_ext.add(i)

        atomic_tp = len(matched_exp)
        atomic_fn = len(exp_atomic) - atomic_tp
        atomic_fp = len(extracted_clauses) - len(matched_ext)

    # 2. Layer B: Canonical Facet Extraction (Multi-label)
    pred_facets = [f for f in prediction.candidate_facets if f]
    exp_facets = case.get("expected_facets", [])
    pred_facet_set = set(pred_facets)
    exp_facet_set = set(exp_facets)

    facet_tp = len(pred_facet_set & exp_facet_set)
    facet_fp = len(pred_facet_set - exp_facet_set)
    facet_fn = len(exp_facet_set - pred_facet_set)

    # 3. Layer C: Canonical Unified Control Ranking & Suppression Safety
    # Collect candidate controls in ranked order
    pred_ctrls_ordered: list[str] = []
    seen_ctrls: set[str] = set()

    for m in prediction.ranked_mappings:
        cid = m.canonical_control_id
        if cid and cid not in seen_ctrls and not m.is_ambiguous and not m.is_suppressed:
            pred_ctrls_ordered.append(cid)
            seen_ctrls.add(cid)

    # If ranked_mappings did not have controls, fall back to candidate_controls
    for cid in prediction.candidate_controls:
        if cid and cid not in seen_ctrls:
            pred_ctrls_ordered.append(cid)
            seen_ctrls.add(cid)

    exp_ctrls = case.get("expected_controls", [])
    exp_ctrl_set = set(exp_ctrls)

    # False-Control Trigger Detection & Candidate Suppression
    false_control_trigger = False
    correct_suppression = False

    if expected_behavior == "must_not_generate_candidates":
        if len(pred_ctrls_ordered) > 0 or len(pred_facet_set) > 0:
            false_control_trigger = True
            correct_suppression = False
        else:
            false_control_trigger = False
            correct_suppression = True
    elif (
        expected_behavior == "undetermined_ambiguity"
        and len(pred_ctrls_ordered) > 0
        and not any(m.is_ambiguous for m in prediction.ranked_mappings)
    ):
        false_control_trigger = True

    # Ranking metrics (Top-1, Top-3, Top-5, MRR)
    top1_match = False
    top3_match = False
    top5_match = False
    reciprocal_rank = 0.0

    if exp_ctrl_set:
        if len(pred_ctrls_ordered) > 0 and pred_ctrls_ordered[0] in exp_ctrl_set:
            top1_match = True
        if any(c in exp_ctrl_set for c in pred_ctrls_ordered[:3]):
            top3_match = True
        if any(c in exp_ctrl_set for c in pred_ctrls_ordered[:5]):
            top5_match = True

        for rank_idx, c in enumerate(pred_ctrls_ordered):
            if c in exp_ctrl_set:
                reciprocal_rank = 1.0 / (rank_idx + 1)
                break

    # 4. Layer F: Numeric Interval AST Validation
    threshold_evaluated = False
    threshold_correct = False
    if case.get("threshold_constraint"):
        threshold_evaluated = True
        exp_t = case["threshold_constraint"]
        pred_t = prediction.threshold_ast
        if pred_t is not None:
            amt_match = abs(pred_t.amount - float(exp_t.get("amount", 0.0))) < 1e-4
            op_match = (pred_t.operator == exp_t.get("operator"))
            threshold_correct = bool(amt_match and op_match)
        else:
            threshold_correct = False

    return CaseEvaluationResult(
        case_id=case_id,
        split=split,
        category=category,
        normative_type=normative_type,
        expected_candidate_behavior=expected_behavior,
        input_length_chars=len(input_text),
        length_tier=length_tier,
        atomic_tp=atomic_tp,
        atomic_fp=atomic_fp,
        atomic_fn=atomic_fn,
        facet_tp=facet_tp,
        facet_fp=facet_fp,
        facet_fn=facet_fn,
        predicted_facets=sorted(pred_facet_set),
        expected_facets=sorted(exp_facet_set),
        top1_match=top1_match,
        top3_match=top3_match,
        top5_match=top5_match,
        reciprocal_rank=reciprocal_rank,
        predicted_controls=pred_ctrls_ordered,
        expected_controls=sorted(exp_ctrl_set),
        false_control_trigger=false_control_trigger,
        correct_suppression=correct_suppression,
        threshold_evaluated=threshold_evaluated,
        threshold_correct=threshold_correct,
        execution_time_ms=prediction.execution_time_ms,
    )


def compute_aggregate_metrics(
    results: list[CaseEvaluationResult],
    canonical_facet_universe: set[str] | None = None,
) -> dict[str, Any]:
    """Compute aggregate statistical metrics across a collection of case evaluation results."""
    total_cases = len(results)
    if total_cases == 0:
        return {"total_cases": 0}

    # Layer A: Atomic Segmentation Aggregates
    atomic_tp_sum = sum(r.atomic_tp for r in results)
    atomic_fp_sum = sum(r.atomic_fp for r in results)
    atomic_fn_sum = sum(r.atomic_fn for r in results)
    atomic_prec = atomic_tp_sum / max(1, atomic_tp_sum + atomic_fp_sum)
    atomic_rec = atomic_tp_sum / max(1, atomic_tp_sum + atomic_fn_sum)
    atomic_f1 = (
        2 * atomic_prec * atomic_rec / max(1e-9, atomic_prec + atomic_rec)
        if (atomic_prec + atomic_rec) > 0
        else 0.0
    )

    # Layer B: Canonical Facet Multi-Label Aggregates
    facet_tp_sum = sum(r.facet_tp for r in results)
    facet_fp_sum = sum(r.facet_fp for r in results)
    facet_fn_sum = sum(r.facet_fn for r in results)
    facet_prec_micro = facet_tp_sum / max(1, facet_tp_sum + facet_fp_sum)
    facet_rec_micro = facet_tp_sum / max(1, facet_tp_sum + facet_fn_sum)
    facet_f1_micro = (
        2 * facet_prec_micro * facet_rec_micro / max(1e-9, facet_prec_micro + facet_rec_micro)
        if (facet_prec_micro + facet_rec_micro) > 0
        else 0.0
    )

    # Unique predicted facets and coverage across 155 UCL facets
    all_pred_facets = set()
    for r in results:
        all_pred_facets.update(r.predicted_facets)
    facet_coverage_count = len(all_pred_facets)
    facet_coverage_rate = (
        facet_coverage_count / len(canonical_facet_universe)
        if canonical_facet_universe
        else 0.0
    )

    # Layer C: Control Level Ranking Aggregates
    cases_with_expected_ctrls = [r for r in results if len(r.expected_controls) > 0]
    n_ctrl_cases = len(cases_with_expected_ctrls)

    top1_acc = (
        sum(1 for r in cases_with_expected_ctrls if r.top1_match) / n_ctrl_cases
        if n_ctrl_cases > 0
        else 0.0
    )
    top3_acc = (
        sum(1 for r in cases_with_expected_ctrls if r.top3_match) / n_ctrl_cases
        if n_ctrl_cases > 0
        else 0.0
    )
    top5_acc = (
        sum(1 for r in cases_with_expected_ctrls if r.top5_match) / n_ctrl_cases
        if n_ctrl_cases > 0
        else 0.0
    )
    mrr = (
        sum(r.reciprocal_rank for r in cases_with_expected_ctrls) / n_ctrl_cases
        if n_ctrl_cases > 0
        else 0.0
    )

    # Control Multi-label Micro F1
    ctrl_tp = sum(len(set(r.predicted_controls) & set(r.expected_controls)) for r in results)
    ctrl_fp = sum(len(set(r.predicted_controls) - set(r.expected_controls)) for r in results)
    ctrl_fn = sum(len(set(r.expected_controls) - set(r.predicted_controls)) for r in results)
    ctrl_prec = ctrl_tp / max(1, ctrl_tp + ctrl_fp)
    ctrl_rec = ctrl_tp / max(1, ctrl_tp + ctrl_fn)
    ctrl_f1 = (
        2 * ctrl_prec * ctrl_rec / max(1e-9, ctrl_prec + ctrl_rec)
        if (ctrl_prec + ctrl_rec) > 0
        else 0.0
    )

    # Layer C & Safety: Candidate Suppression & False-Control Triggers
    suppressed_cases = [
        r for r in results if r.expected_candidate_behavior == "must_not_generate_candidates"
    ]
    n_suppressed = len(suppressed_cases)
    correct_suppressions = sum(1 for r in suppressed_cases if r.correct_suppression)
    suppression_accuracy = (
        correct_suppressions / n_suppressed if n_suppressed > 0 else 1.0
    )
    false_triggers_on_suppressed = sum(1 for r in suppressed_cases if r.false_control_trigger)
    false_trigger_rate = (
        false_triggers_on_suppressed / n_suppressed if n_suppressed > 0 else 0.0
    )

    total_false_triggers = sum(1 for r in results if r.false_control_trigger)

    # Layer F: Numeric Interval AST Aggregates
    threshold_cases = [r for r in results if r.threshold_evaluated]
    n_thresh = len(threshold_cases)
    threshold_correct_count = sum(1 for r in threshold_cases if r.threshold_correct)
    threshold_accuracy = (
        threshold_correct_count / n_thresh if n_thresh > 0 else 1.0
    )

    # Latency Aggregates
    latencies = [r.execution_time_ms for r in results]
    mean_latency = statistics.mean(latencies) if latencies else 0.0
    p50_latency = statistics.median(latencies) if latencies else 0.0
    p95_latency = (
        statistics.quantiles(latencies, n=20)[18]
        if len(latencies) >= 20
        else max(latencies) if latencies else 0.0
    )

    return {
        "total_cases": total_cases,
        "layer_a_atomic": {
            "tp": atomic_tp_sum,
            "fp": atomic_fp_sum,
            "fn": atomic_fn_sum,
            "precision": round(atomic_prec, 4),
            "recall": round(atomic_rec, 4),
            "f1": round(atomic_f1, 4),
        },
        "layer_b_facets": {
            "tp": facet_tp_sum,
            "fp": facet_fp_sum,
            "fn": facet_fn_sum,
            "precision_micro": round(facet_prec_micro, 4),
            "recall_micro": round(facet_rec_micro, 4),
            "f1_micro": round(facet_f1_micro, 4),
            "unique_facets_predicted": facet_coverage_count,
            "canonical_facet_coverage_rate": round(facet_coverage_rate, 4),
        },
        "layer_c_controls": {
            "cases_with_targets": n_ctrl_cases,
            "top1_recall": round(top1_acc, 4),
            "top3_recall": round(top3_acc, 4),
            "top5_recall": round(top5_acc, 4),
            "mrr": round(mrr, 4),
            "micro_precision": round(ctrl_prec, 4),
            "micro_recall": round(ctrl_rec, 4),
            "micro_f1": round(ctrl_f1, 4),
        },
        "layer_c_normative_safety": {
            "suppression_target_cases": n_suppressed,
            "correct_suppressions": correct_suppressions,
            "suppression_accuracy": round(suppression_accuracy, 4),
            "false_triggers_on_suppressed": false_triggers_on_suppressed,
            "false_trigger_rate": round(false_trigger_rate, 4),
            "total_false_triggers": total_false_triggers,
        },
        "layer_f_thresholds": {
            "total_threshold_cases": n_thresh,
            "correct_thresholds": threshold_correct_count,
            "threshold_accuracy": round(threshold_accuracy, 4),
        },
        "performance_latency_ms": {
            "mean": round(mean_latency, 2),
            "p50": round(p50_latency, 2),
            "p95": round(p95_latency, 2),
        },
    }


def evaluate_dataset(
    engine: Any,
    cases: list[dict[str, Any]],
    canonical_facet_universe: set[str] | None = None,
) -> dict[str, Any]:
    """Execute evaluation for an engine across a list of benchmark cases."""
    case_results: list[CaseEvaluationResult] = []

    for case in cases:
        input_text = case["input_text"]
        t0 = time.perf_counter()
        prediction: ExtractionResult = engine.extract_and_map(
            input_text=input_text,
            case_id=case.get("case_id", ""),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        prediction.execution_time_ms = elapsed_ms

        res = evaluate_case(prediction, case)
        case_results.append(res)

    overall_metrics = compute_aggregate_metrics(case_results, canonical_facet_universe)

    # Stratified Slices
    # 1. By Split
    by_split: dict[str, Any] = {}
    splits = sorted({r.split for r in case_results})
    for s in splits:
        sub = [r for r in case_results if r.split == s]
        by_split[s] = compute_aggregate_metrics(sub, canonical_facet_universe)

    # 2. By Normative Class
    by_normative_class: dict[str, Any] = {}
    norm_classes = sorted({r.normative_type for r in case_results})
    for nc in norm_classes:
        sub = [r for r in case_results if r.normative_type == nc]
        by_normative_class[nc] = compute_aggregate_metrics(sub, canonical_facet_universe)

    # 3. By Category
    by_category: dict[str, Any] = {}
    categories = sorted({r.category for r in case_results})
    for cat in categories:
        sub = [r for r in case_results if r.category == cat]
        by_category[cat] = compute_aggregate_metrics(sub, canonical_facet_universe)

    # 4. By Length Tier
    by_length_tier: dict[str, Any] = {}
    for tier in ["short", "medium", "long"]:
        sub = [r for r in case_results if r.length_tier == tier]
        if sub:
            by_length_tier[tier] = compute_aggregate_metrics(sub, canonical_facet_universe)

    return {
        "overall": overall_metrics,
        "by_split": by_split,
        "by_normative_class": by_normative_class,
        "by_category": by_category,
        "by_length_tier": by_length_tier,
        "individual_case_results": [r.to_dict() for r in case_results],
    }
