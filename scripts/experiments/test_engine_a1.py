"""Unit tests for Enhanced Deterministic Rules Engine (A1)."""

from scripts.experiments.engine_a1 import EngineA1


def test_engine_a1_affirmative_extraction():
    engine = EngineA1()
    text = "Enterprise network administrators must enforce TLS 1.3 encryption on all external API telemetry pipelines carrying customer information."
    res = engine.extract_and_map(text, case_id="TEST-A1-AFF")

    assert not res.is_suppressed
    assert "controls_commensurate" in res.candidate_facets
    assert "CTRL-SEC-COMMENSURATE" in res.candidate_controls
    assert len(res.ranked_mappings) >= 1
    assert res.ranked_mappings[0].review_status == "proposed"


def test_engine_a1_prohibition_suppression():
    engine = EngineA1()
    text = "Personnel are strictly prohibited from transmitting unencrypted customer information over public networks under any circumstances."
    res = engine.extract_and_map(text, case_id="TEST-A1-PROHIB")

    assert res.is_suppressed
    assert len(res.candidate_controls) == 0
    assert len(res.candidate_facets) == 0
    assert len(res.ranked_mappings) == 0
    assert res.detected_normative_type == "prohibition_absolute"


def test_engine_a1_exemption_suppression():
    engine = EngineA1()
    text = "Generative AI prototypes running in segregated non-production sandboxes are exempt from enterprise model registry registration."
    res = engine.extract_and_map(text, case_id="TEST-A1-EXEMPT")

    assert res.is_suppressed
    assert len(res.candidate_controls) == 0
    assert res.detected_normative_type == "scope_exemption"


def test_engine_a1_aspirational_suppression():
    engine = EngineA1()
    text = "The digital engineering department aims to champion proactive cybersecurity mindfulness across our product communities."
    res = engine.extract_and_map(text, case_id="TEST-A1-ASPIR")

    assert res.is_suppressed
    assert len(res.candidate_controls) == 0
    assert res.detected_normative_type == "aspirational_statement"


def test_engine_a1_threshold_ast_parsing():
    engine = EngineA1()
    text = "Automated payment routing decisions exceeding AUD $250,000 must obtain dual-delegation approval from an Authorised Officer before payment release."
    res = engine.extract_and_map(text, case_id="TEST-A1-THRESH")

    assert not res.is_suppressed
    assert res.threshold_ast is not None
    assert res.threshold_ast.amount == 250000.0
    assert res.threshold_ast.operator == ">"
    assert res.threshold_ast.currency == "AUD"
    assert "CTRL-DELEGATED-AUTHORITY-THRESHOLD" in res.candidate_controls
