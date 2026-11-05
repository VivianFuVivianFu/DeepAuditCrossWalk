"""Unit test for Historical Production Baseline Engine (A0)."""

from scripts.experiments.engine_a0 import EngineA0


def test_engine_a0_basic_execution():
    engine = EngineA0()
    text = "All credit transactions over AUD $500,000 must obtain dual sign-off before payment."
    res = engine.extract_and_map(text, case_id="TEST-A0")

    assert res.case_id == "TEST-A0"
    assert len(res.extracted_clauses) >= 1
    assert "human_approval_required" in res.candidate_facets
    assert "approval_threshold_defined" in res.candidate_facets
    assert "pre_execution_block" in res.candidate_facets
    assert "CTRL-DELEGATED-AUTHORITY-THRESHOLD" in res.candidate_controls
    assert res.threshold_ast is not None
    assert res.threshold_ast.amount == 500000.0
    assert res.execution_time_ms > 0
    assert not res.is_suppressed
