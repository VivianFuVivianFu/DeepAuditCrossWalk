import hashlib
import json
from pathlib import Path

import pytest

from banking_crosswalk.models import ReconciliationRelationship
from banking_crosswalk.llm.eval_harness import (
    build_eval_runtime_config,
    evaluate_clause_benchmark,
)
from banking_crosswalk.llm.types import SemanticMatchingMode
from e31_calibration_dataset import AdversarialCalibrationClause
from test_e32_live_gemini_validation import _doc_bytes


EXPECTED_E36_SHA256 = "d4b359d3b58305cd5506e3b085e0f88e820bbaa551471caf852a4a6dfd323bd1"


def _load_e36_dataset():
    root = Path(__file__).resolve().parents[2]
    dataset_file = root / "E36_INDEPENDENT_EVALUATION_DATASET.json"
    assert dataset_file.exists(), f"Missing dataset file at {dataset_file}"

    content_bytes = dataset_file.read_bytes()
    computed_sha = hashlib.sha256(content_bytes).hexdigest()
    assert (
        computed_sha == EXPECTED_E36_SHA256
    ), f"E3.6 dataset fingerprint mismatch: expected {EXPECTED_E36_SHA256}, got {computed_sha}"

    data = json.loads(content_bytes.decode("utf-8"))
    clauses = [
        AdversarialCalibrationClause(
            case_id=c["case_id"],
            split="held_out",
            org_id=c["org_id"],
            doc_filename=c["doc_filename"],
            doc_format=c["doc_format"],
            raw_text=c["raw_text"],
            phenomenon=c["phenomenon"],
            ground_truth_obligation_id=c["ground_truth_obligation_id"],
            ground_truth_relationship=ReconciliationRelationship(c["ground_truth_relationship"]),
            expects_human_resolution=c["expects_human_resolution"],
            expected_obligation_ids=tuple(c["expected_obligation_ids"]),
        )
        for c in data["clauses"]
    ]
    return clauses


def test_e36_dataset_fingerprint_and_schema():
    """Verify that E36 independent evaluation dataset is immutable and has 30 valid clauses."""
    clauses = _load_e36_dataset()
    assert len(clauses) == 30
    assert len({c.case_id for c in clauses}) == 30


def test_e36_deterministic_independent_evaluation():
    """Evaluate deterministic pipeline against frozen E3.6 independent dataset."""
    clauses = _load_e36_dataset()
    cfg = build_eval_runtime_config(mode=SemanticMatchingMode.DISABLED, provider="mock")
    res = evaluate_clause_benchmark(
        clauses,
        mode=SemanticMatchingMode.DISABLED,
        provider="mock",
        config=cfg,
        doc_bytes_builder=_doc_bytes,
    )

    # Candidate retrieval reliability
    assert res["recall_at_5"] >= 25  # 27 / 29 (93.1%)
    assert res["recall_at_1"] >= 20  # 23 / 29 (79.3%)

    # Critical governance safety invariants
    assert res["false_coverage"] == 0
    assert res["false_equivalence"] == 0
    assert res["unresolved_flagged"] == res["unresolved_total"]


def test_e36_mock_hybrid_independent_evaluation():
    """Evaluate mock hybrid pipeline against frozen E3.6 independent dataset."""
    clauses = _load_e36_dataset()
    cfg = build_eval_runtime_config(mode=SemanticMatchingMode.HYBRID, provider="mock")
    res = evaluate_clause_benchmark(
        clauses,
        mode=SemanticMatchingMode.HYBRID,
        provider="mock",
        config=cfg,
        doc_bytes_builder=_doc_bytes,
    )

    # Retrieval and safety checks
    assert res["recall_at_5"] >= 24  # 25 / 29 (86.2%)
    assert res["false_coverage"] == 0
    assert res["false_equivalence"] == 0
