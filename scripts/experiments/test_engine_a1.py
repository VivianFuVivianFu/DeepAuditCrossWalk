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
    # 1. Anti-control prohibition (forbidding a beneficial governance control) MUST be suppressed
    anti_control_text = "Consumer credit scoring models shall not implement automated bias testing using synthetic demographic proxies."
    res_suppressed = engine.extract_and_map(anti_control_text, case_id="TEST-A1-CTRL-PROHIB")

    assert res_suppressed.is_suppressed
    assert len(res_suppressed.candidate_controls) == 0
    assert len(res_suppressed.candidate_facets) == 0
    assert len(res_suppressed.ranked_mappings) == 0
    assert res_suppressed.detected_normative_type == "control_prohibition"

    # 2. Protective prohibition (prohibiting unencrypted transmission) expresses a preventive control and MUST NOT be suppressed in revised mode
    protective_text = "Personnel are strictly prohibited from transmitting unencrypted customer information over public networks under any circumstances."
    res_protective = engine.extract_and_map(protective_text, case_id="TEST-A1-PROT-PROHIB")
    assert not res_protective.is_suppressed
    assert res_protective.detected_normative_type == "protective_prohibition"
    assert "controls_commensurate" in res_protective.candidate_facets
    assert "CTRL-SEC-COMMENSURATE" in res_protective.candidate_controls

    # 3. Historical P1B-1 mode preserves original syntactic suppression behaviour for reproducibility
    hist_engine = EngineA1(normative_mode="historical_p1b1")
    res_hist = hist_engine.extract_and_map(protective_text, case_id="TEST-A1-HIST-PROHIB")
    assert res_hist.is_suppressed
    assert res_hist.detected_normative_type == "prohibition_absolute"


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


def test_engine_a1_decomposed_v020_facets_evidence_separation():
    """Verify EngineA1 distinguishes technical vs organisational security and log retention vs oversight."""
    engine = EngineA1()
    assert "security_controls_defined" not in engine.FACET_REGEX_PATTERNS
    assert "security_controls_defined" not in engine.FACET_TO_CANONICAL_CONTROL

    # Technical security evidence only (P1-009 pattern) -> must NOT infer organisational_security_measures_implemented
    tech_res = engine.extract_and_map(
        "Customer training datasets must be secured using AES-256 encryption at rest and isolated within private tenant VPCs.",
        case_id="TEST-A1-TECH-SEC",
    )
    assert "technical_security_measures_implemented" in tech_res.candidate_facets
    assert "organisational_security_measures_implemented" not in tech_res.candidate_facets
    assert "CTRL-PRIV-SECURITY-RETENTION" in tech_res.candidate_controls

    # Organisational security evidence only -> must NOT infer technical_security_measures_implemented
    org_res = engine.extract_and_map(
        "All staff handling personal information must complete annual staff privacy training and follow documented information handling procedures.",
        case_id="TEST-A1-ORG-SEC",
    )
    assert "organisational_security_measures_implemented" in org_res.candidate_facets
    assert "technical_security_measures_implemented" not in org_res.candidate_facets
    assert "CTRL-PRIV-SECURITY-RETENTION" in org_res.candidate_controls

    # EU AI Act Art 26(6) 6-month log retention only (P1-151 pattern) -> must NOT infer deployer_human_oversight_assigned
    log_res = engine.extract_and_map(
        "Deployers of High-Risk credit evaluation AI systems must retain system logs generated by the AI system for at least 6 months under Article 26.",
        case_id="TEST-A1-EU-LOG",
    )
    assert "automatic_logs_retained_6months" in log_res.candidate_facets
    assert "deployer_human_oversight_assigned" not in log_res.candidate_facets
    assert "CTRL-EU-HIGH-RISK" in log_res.candidate_controls


def test_engine_a1_distinguishes_waivers_missing_impl_and_protective_prohibitions():
    """Verify waivers and missing implementation are suppressed while protective prohibitions are retained."""
    engine = EngineA1()

    waiver_res = engine.extract_and_map(
        "Dual human approval is waived for internal low-value test transfers.",
        case_id="TEST-A1-WAIVER",
    )
    assert waiver_res.is_suppressed
    assert waiver_res.detected_normative_type == "control_waiver"

    missing_res = engine.extract_and_map(
        "The legacy analytics platform does not currently implement encryption at rest.",
        case_id="TEST-A1-MISSING",
    )
    assert missing_res.is_suppressed
    assert missing_res.detected_normative_type == "missing_implementation"

    protective_res = engine.extract_and_map(
        "Employees must not transmit unencrypted customer information.",
        case_id="TEST-A1-PROTECTIVE",
    )
    assert not protective_res.is_suppressed
    assert protective_res.detected_normative_type == "protective_prohibition"
    assert "controls_commensurate" in protective_res.candidate_facets
    assert "CTRL-SEC-COMMENSURATE" in protective_res.candidate_controls

