"""Unit tests for Canonical Mapping Adapter in Phase P1B experiments."""

import json
import re
from pathlib import Path

import pytest

from scripts.experiments.canonical_adapter import CanonicalMappingAdapter
from scripts.experiments.models import CandidatePrediction

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UCL_PATH = REPO_ROOT / "UNIFIED_CONTROL_LIBRARY.json"
BACKEND_DATA_DIR = REPO_ROOT / "backend" / "banking_crosswalk" / "data"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def adapter():
    return CanonicalMappingAdapter()


@pytest.fixture
def ucl_data():
    return _load_json(UCL_PATH)


def test_adapter_loads_complete_taxonomy(adapter, ucl_data):
    """Test that adapter loads controls and facets dynamically from the canonical UCL."""
    controls = ucl_data["controls"]
    expected_controls = {c["control_id"] for c in controls}
    expected_facets = {
        facet for c in controls for facet in c.get("control_facets", [])
    }

    assert adapter.canonical_controls == expected_controls
    assert adapter.canonical_facets == expected_facets
    assert adapter.canonical_control_count == len(expected_controls)
    assert adapter.canonical_facet_count == len(expected_facets)
    if "total_controls" in ucl_data:
        assert adapter.canonical_control_count == ucl_data["total_controls"]

    # Confirm source-supported E4.1 canonical facets are preserved (not stripped back to 155)
    e41_added_facets = {
        "technical_security_measures_implemented",
        "organisational_security_measures_implemented",
        "deployer_human_oversight_assigned",
        "automatic_logs_retained_6months",
        "synthetic_content_marking_and_disclosure_applied",
    }
    assert e41_added_facets.issubset(adapter.canonical_facets)


def test_ucl_unique_control_ids_and_facet_ids(ucl_data):
    """Verify control IDs and facet IDs are unique, non-empty, and well-formed."""
    controls = ucl_data["controls"]
    control_ids = [c["control_id"] for c in controls]
    assert len(control_ids) == len(set(control_ids)), "Duplicate control_id values in UCL"
    assert len(control_ids) == ucl_data["total_controls"]

    seen_facets: dict[str, str] = {}
    for control in controls:
        cid = control["control_id"]
        facets = control.get("control_facets", [])
        assert facets, f"Control '{cid}' must define at least one canonical facet"
        assert len(facets) == len(set(facets)), f"Duplicate facets inside control '{cid}'"
        for facet in facets:
            assert re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", facet), (
                f"Facet '{facet}' in '{cid}' must be canonical snake_case"
            )
            assert facet not in seen_facets, (
                f"Facet '{facet}' duplicated across controls '{seen_facets[facet]}' and '{cid}'"
            )
            seen_facets[facet] = cid


def test_library_parity_root_vs_backend_data():
    """Verify root canonical JSON libraries match packaged backend data copies."""
    pairs = [
        (REPO_ROOT / "UNIFIED_CONTROL_LIBRARY.json", BACKEND_DATA_DIR / "unified_control_library.json"),
        (REPO_ROOT / "ATOMIC_OBLIGATION_CATALOGUE.json", BACKEND_DATA_DIR / "atomic_obligation_catalogue.json"),
        (REPO_ROOT / "OBLIGATION_CONTROL_MAPPINGS.json", BACKEND_DATA_DIR / "obligation_control_mappings.json"),
    ]
    for root_file, backend_file in pairs:
        assert _load_json(root_file) == _load_json(backend_file), (
            f"Library parity mismatch between {root_file.name} and {backend_file.name}"
        )


def test_all_adapter_aliases_and_translations_valid(adapter, tmp_path, ucl_data):
    """Verify all adapter alias targets exist in canonical UCL and fail fast if missing."""
    assert not (
        set(adapter.VERIFIED_CONTROL_ALIASES) & set(adapter.AMBIGUOUS_CONTROL_ALIASES)
    ), "Control alias cannot be both verified and ambiguous"

    for legacy_id, target_cid in adapter.VERIFIED_CONTROL_ALIASES.items():
        assert target_cid in adapter.canonical_controls, (
            f"VERIFIED_CONTROL_ALIASES['{legacy_id}'] references missing control '{target_cid}'"
        )

    for legacy_id, candidate_cids in adapter.AMBIGUOUS_CONTROL_ALIASES.items():
        assert len(candidate_cids) >= 2
        for candidate_cid in candidate_cids:
            assert candidate_cid in adapter.canonical_controls, (
                f"AMBIGUOUS_CONTROL_ALIASES['{legacy_id}'] references missing control '{candidate_cid}'"
            )

    for legacy_facet, target_facets in adapter.FACET_TRANSLATIONS.items():
        assert target_facets, f"Empty facet translation for '{legacy_facet}'"
        for target_facet in target_facets:
            assert target_facet in adapter.canonical_facets, (
                f"FACET_TRANSLATIONS['{legacy_facet}'] references missing facet '{target_facet}'"
            )

    # Ensure dynamic integrity check rejects a custom UCL missing a mapped target facet
    broken_ucl = json.loads(json.dumps(ucl_data))
    for control in broken_ucl["controls"]:
        control["control_facets"] = [
            f for f in control["control_facets"] if f != "retention_schedule_applied"
        ]
    broken_path = tmp_path / "broken_ucl.json"
    broken_path.write_text(json.dumps(broken_ucl), encoding="utf-8")
    with pytest.raises(AssertionError, match="retention_schedule_applied"):
        CanonicalMappingAdapter(ucl_path=broken_path)


def test_regulatory_catalogue_and_mappings_valid_control_and_facet_references(adapter):
    """Verify obligation catalogue and mappings reference only valid canonical controls and facets."""
    catalogue = _load_json(REPO_ROOT / "ATOMIC_OBLIGATION_CATALOGUE.json")
    obligations = catalogue.get("obligations", catalogue.get("records", []))
    assert obligations, "Obligation catalogue must not be empty"

    for ob in obligations:
        oid = ob["obligation_id"]
        for cid in ob.get("unified_controls", []):
            assert cid in adapter.canonical_controls, (
                f"Obligation '{oid}' references unknown control '{cid}'"
            )
        for facet in ob.get("coverage_facets", []):
            assert facet in adapter.canonical_facets, (
                f"Obligation '{oid}' references unknown facet '{facet}'"
            )

    mappings_doc = _load_json(REPO_ROOT / "OBLIGATION_CONTROL_MAPPINGS.json")
    mappings = mappings_doc.get("mappings", [])
    assert mappings, "Obligation-control mappings must not be empty"

    for m in mappings:
        mid = m.get("mapping_id", m.get("obligation_id"))
        cid = m["control_id"]
        assert cid in adapter.canonical_controls, (
            f"Mapping '{mid}' references unknown control '{cid}'"
        )
        mapped_facets = m.get("mapped_facets", [])
        if m.get("mapping_relationship") == "non_equivalent":
            assert mapped_facets == [], (
                f"Non-equivalent mapping '{mid}' must not populate mapped_facets"
            )
        else:
            assert mapped_facets, f"Mapping '{mid}' must declare non-empty mapped_facets"
        for facet in mapped_facets:
            assert facet in adapter.canonical_facets, (
                f"Mapping '{mid}' references unknown facet '{facet}'"
            )


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
    """Test facet translations against canonical UCL facets."""
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


def test_version_aware_facet_migration_categories(adapter):
    """Test all 5 version-aware migration classifications and evidence-gated decomposition."""
    # 1. Exact rename (1:1)
    rec_exact = adapter.migrate_legacy_facet("bias_testing", source_text="Perform quarterly bias testing.")
    assert rec_exact.migration_kind == "exact_rename"
    assert rec_exact.emitted_facets == ["fairness_and_explainability_metrics_evaluated"]
    assert rec_exact.unresolved_candidate_facets == []
    assert rec_exact.canonical_control_id == "CTRL-AI-DRIFT-MONITORING"

    # 2a. One-to-many decomposition: P1-009 (technical security evidence only)
    p1_009_text = (
        "Customer training datasets must be secured using AES-256 encryption at rest "
        "and isolated within private tenant VPCs."
    )
    rec_p1_009 = adapter.migrate_legacy_facet("security_controls_defined", source_text=p1_009_text)
    assert rec_p1_009.migration_kind == "one_to_many_decomposition"
    assert rec_p1_009.emitted_facets == ["technical_security_measures_implemented"]
    assert rec_p1_009.unresolved_candidate_facets == ["organisational_security_measures_implemented"]
    assert rec_p1_009.canonical_control_id == "CTRL-PRIV-SECURITY-RETENTION"
    assert rec_p1_009.requires_human_review is True

    # 2b. One-to-many decomposition: P1-151 (6-month log retention evidence only)
    p1_151_text = (
        "Deployers of High-Risk credit evaluation AI systems must retain system logs "
        "generated by the AI system for at least 6 months under Article 26."
    )
    rec_p1_151 = adapter.migrate_legacy_facet(
        "deployer_human_oversight_and_6month_log_retention",
        source_text=p1_151_text,
    )
    assert rec_p1_151.migration_kind == "one_to_many_decomposition"
    assert rec_p1_151.emitted_facets == ["automatic_logs_retained_6months"]
    assert rec_p1_151.unresolved_candidate_facets == ["deployer_human_oversight_assigned"]
    assert rec_p1_151.canonical_control_id == "CTRL-EU-HIGH-RISK"
    assert rec_p1_151.requires_human_review is True

    # 3. Ambiguous legacy mapping (broad cue without sub-facet evidence)
    rec_ambig = adapter.migrate_legacy_facet(
        "security_controls_defined",
        source_text="The entity must maintain reasonable security controls to safeguard personal information.",
    )
    assert rec_ambig.migration_kind == "ambiguous_legacy_mapping"
    assert rec_ambig.emitted_facets == []
    assert set(rec_ambig.unresolved_candidate_facets) == {
        "technical_security_measures_implemented",
        "organisational_security_measures_implemented",
    }

    # 4. Missing evidence (empty or unrelated source text for retired facet)
    rec_missing = adapter.migrate_legacy_facet("security_controls_defined", source_text="")
    assert rec_missing.migration_kind == "missing_evidence"
    assert rec_missing.emitted_facets == []
    assert len(rec_missing.unresolved_candidate_facets) == 2

    # 5. Unsupported legacy facet
    rec_unsupported = adapter.migrate_legacy_facet("fictitious_nonexistent_facet", source_text="Any text.")
    assert rec_unsupported.migration_kind == "unsupported_legacy_facet"
    assert rec_unsupported.emitted_facets == []
    assert rec_unsupported.unresolved_candidate_facets == []


def test_v020_aligned_dataset_preserves_historical_v2_and_migrates_retired_facets(adapter):
    """Verify build_v020_aligned_dataset migrates P1-009 and P1-151 without mutating V2."""
    v2_data = _load_json(REPO_ROOT / "P1_EVALUATION_DATASET_V2.json")
    aligned = adapter.build_v020_aligned_dataset(v2_data)

    # Original V2 must remain unmodified
    orig_009 = next(c for c in v2_data["cases"] if c["case_id"] == "P1-009")
    orig_151 = next(c for c in v2_data["cases"] if c["case_id"] == "P1-151")
    assert orig_009["expected_facets"] == ["security_controls_defined"]
    assert orig_151["expected_facets"] == ["deployer_human_oversight_and_6month_log_retention"]

    # Migrated v0.2.0 view must have 100% canonical v0.2.0 facets and preserve audit trail
    mig_009 = next(c for c in aligned["cases"] if c["case_id"] == "P1-009")
    mig_151 = next(c for c in aligned["cases"] if c["case_id"] == "P1-151")
    assert mig_009["expected_facets"] == ["technical_security_measures_implemented"]
    assert mig_009["legacy_taxonomy_migration"]["unresolved_candidate_facets"] == [
        "organisational_security_measures_implemented"
    ]
    assert mig_151["expected_facets"] == ["automatic_logs_retained_6months"]
    assert mig_151["legacy_taxonomy_migration"]["unresolved_candidate_facets"] == [
        "deployer_human_oversight_assigned"
    ]

    for case in aligned["cases"]:
        for facet in case.get("expected_facets", []):
            assert facet in adapter.canonical_facets, (
                f"Case {case['case_id']} contains non-canonical facet {facet}"
            )

