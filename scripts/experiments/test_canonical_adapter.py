"""Unit tests for Canonical Mapping Adapter in Phase P1B experiments."""

import pytest

from scripts.experiments.canonical_adapter import CanonicalMappingAdapter
from scripts.experiments.models import CandidatePrediction


@pytest.fixture
def adapter():
    return CanonicalMappingAdapter()


def test_adapter_loads_complete_taxonomy(adapter):
    """Test that adapter loads exactly 33 controls and 155 facets from UCL."""
    assert len(adapter.canonical_controls) == 33
    assert len(adapter.canonical_facets) == 155


def test_exact_canonical_control_resolution(adapter):
    """Test that exact canonical control IDs resolve to themselves."""
    for cid in ["CTRL-PRIV-GOVERNANCE", "CTRL-SEC-INCIDENT", "CTRL-AI-DRIFT-MONITORING"]:
        resolved, is_ambig, _reason = adapter.resolve_control_id(cid)
        assert resolved == cid
        assert not is_ambig


def test_verified_legacy_aliases_resolution(adapter):
    """Test that verified legacy aliases resolve to the proper canonical control IDs."""
    test_cases = {
        "CTRL-FIN-APPROVAL-THRESHOLDS": "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "CTRL-GOV-OVERSIGHT": "CTRL-HUMAN-OVERSIGHT",
        "CTRL-FAIR-BIAS-DETECTION": "CTRL-AI-DRIFT-MONITORING",
        "CTRL-FAIR-BIAS-EVALUATION": "CTRL-AI-DRIFT-MONITORING",
        "CTRL-DATA-RETENTION-DISPOSAL": "CTRL-PRIV-SECURITY-RETENTION",
        "CTRL-COMPL-DISPUTE-RESOLUTION": "CTRL-IDR-HANDLING",
        "CTRL-GOV-AUDITABILITY": "CTRL-INDEPENDENT-AUDIT-ASSURANCE",
        "CTRL-DATA-PRIVACY-RIGHTS": "CTRL-PRIV-ACCESS-CORRECTION",
        "CTRL-TECH-INCIDENT-RESPONSE": "CTRL-SEC-INCIDENT",
        "CTRL-TECH-ACCESS-SECURITY": "CTRL-SEC-COMMENSURATE",
        "CTRL-TPS-VENDOR-ASSESSMENT": "CTRL-THIRD-PARTY-AI",
        "CTRL-OPS-OUTSOURCING": "CTRL-THIRD-PARTY-AI",
    }
    for legacy_id, expected_canonical in test_cases.items():
        resolved, is_ambig, _reason = adapter.resolve_control_id(legacy_id)
        assert resolved == expected_canonical, f"Failed for {legacy_id}"
        assert not is_ambig
        assert resolved in adapter.canonical_controls


def test_ambiguous_legacy_aliases_flagged(adapter):
    """Test that ambiguous legacy IDs are marked ambiguous and not arbitrarily forced."""
    for ambig_id in ["CTRL-GOV-FRAMEWORK", "CTRL-TECH-OBSERVABILITY"]:
        resolved, is_ambig, reason = adapter.resolve_control_id(ambig_id)
        assert resolved is None, f"Ambiguous ID {ambig_id} should not resolve to concrete ID"
        assert is_ambig is True
        assert "Ambiguous legacy identifier" in reason


def test_unknown_control_identifier(adapter):
    """Test that unknown identifiers return None and not ambiguous."""
    resolved, is_ambig, reason = adapter.resolve_control_id("CTRL-UNKNOWN-FICTITIOUS")
    assert resolved is None
    assert is_ambig is False
    assert "Unknown control identifier" in reason


def test_facet_resolution_exact_and_aliases(adapter):
    """Test facet translations against canonical 155 facets."""
    # Exact canonical strings
    assert adapter.resolve_facets("human_approval_required") == ["human_approval_required"]
    assert adapter.resolve_facets("approval_threshold_defined") == ["approval_threshold_defined"]
    assert adapter.resolve_facets("pre_execution_block") == ["pre_execution_block"]

    # Verified aliases
    zero_ret = adapter.resolve_facets("zero_data_retention")
    assert "retention_schedule_applied" in zero_ret
    assert "destruction_or_deidentification_verified" in zero_ret
    for f in zero_ret:
        assert f in adapter.canonical_facets

    prompt_log = adapter.resolve_facets("prompt_logging")
    assert "approval_logs_retained" in prompt_log
    assert "incident_detection_defined" in prompt_log
    for f in prompt_log:
        assert f in adapter.canonical_facets

    bias = adapter.resolve_facets("bias_testing")
    assert bias == ["fairness_and_explainability_metrics_evaluated"]
    assert bias[0] in adapter.canonical_facets

    inv = adapter.resolve_facets("model_inventory")
    assert "use_case_registered_in_enterprise_ai_inventory" in inv
    for f in inv:
        assert f in adapter.canonical_facets


def test_candidate_prediction_review_status_invariant():
    """Test that CandidatePrediction enforces review_status='proposed'."""
    p = CandidatePrediction(
        clause_id="POL-01",
        canonical_control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        review_status="proposed",
    )
    assert p.review_status == "proposed"

    with pytest.raises(ValueError):
        CandidatePrediction(
            clause_id="POL-01",
            canonical_control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
            review_status="approved",  # Must be rejected!
        )
