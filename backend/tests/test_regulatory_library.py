"""Automated tests for the expanded Australian Banking AI Governance Regulatory & Control Library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from banking_crosswalk.catalog import (
    load_aiaf_question_bank,
    load_atomic_obligation_catalogue,
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_source_register,
    load_unified_control_library,
)
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import Authority, ReviewStatus
from banking_crosswalk.policy import assess_policy_gaps, extract_policy_pack
from banking_crosswalk.validation import (
    run_synthetic_evaluation_suite,
    validate_regulatory_library,
)


ROOT = Path(__file__).resolve().parents[2]


def test_required_deliverable_files_exist_and_load():
    for filename in [
        "REGULATORY_SOURCE_REGISTER.csv",
        "REGULATORY_COVERAGE_AUDIT.md",
        "ATOMIC_OBLIGATION_CATALOGUE.json",
        "UNIFIED_CONTROL_LIBRARY.json",
        "OBLIGATION_CONTROL_MAPPINGS.json",
        "APPLICABILITY_RULES.md",
        "REGULATORY_LIBRARY_VALIDATION_REPORT.md",
    ]:
        assert (ROOT / filename).exists(), f"Missing deliverable: {filename}"

    sources = load_source_register(ROOT / "REGULATORY_SOURCE_REGISTER.csv")
    obligations = load_atomic_obligation_catalogue(
        ROOT / "ATOMIC_OBLIGATION_CATALOGUE.json"
    )
    controls = load_unified_control_library(ROOT / "UNIFIED_CONTROL_LIBRARY.json")
    mappings = load_obligation_control_mappings(
        ROOT / "OBLIGATION_CONTROL_MAPPINGS.json"
    )
    pack = load_regulatory_pack()

    assert len(sources) == 17
    assert len(obligations) == 45
    assert len(controls.controls) == 33
    assert len(mappings.mappings) == 55
    assert len(pack.obligations) == 45
    assert all(ob.review_status == ReviewStatus.PROPOSED for ob in obligations)
    assert all(m.review_status == ReviewStatus.PROPOSED for m in mappings.mappings)


def test_all_nine_automated_validation_checks_pass():
    report = validate_regulatory_library()
    assert report["valid"] is True
    assert report["technical_validation_passed"] is True
    assert report["legal_review_status"] == "pending_expert_human_review"
    for check_name, check_result in report["checks"].items():
        assert check_result["passed"] is True, (
            f"Check {check_name} failed: {check_result['errors']}"
        )


def test_validation_detects_injected_defects():
    pack = load_regulatory_pack()
    bad_ob = pack.obligations[0].model_copy(
        update={
            "source_id": "NON-EXISTENT-SOURCE",
            "provision": "no_token_here",
            "source_url": "http://insecure.example.com",
            "effective_from": pack.obligations[0].effective_from,
            "effective_to": "1900-01-01",
            "authority": Authority.VOLUNTARY,
            "applicability_key": "unknown_rule_key",
            "control_id": "CTRL-MISSING",
            "review_status": ReviewStatus.APPROVED,
        }
    )
    dup_ob = pack.obligations[1].model_copy()
    broken_pack = pack.model_copy(
        update={"obligations": [bad_ob, dup_ob, dup_ob, *pack.obligations[2:]]}
    )
    report = validate_regulatory_library(pack=broken_pack)
    assert report["valid"] is False
    assert not report["checks"]["missing_source_references"]["passed"]
    assert not report["checks"]["invalid_provision_references"]["passed"]
    assert not report["checks"]["duplicate_obligations"]["passed"]
    assert not report["checks"]["unmapped_control_facets"]["passed"]
    assert not report["checks"]["conflicting_effective_dates"]["passed"]
    assert not report["checks"]["incorrect_legal_authority_classification"]["passed"]
    assert not report["checks"]["unreviewed_mappings"]["passed"]
    assert not report["checks"]["unsupported_applicability_decisions"]["passed"]


def test_synthetic_evaluation_suite_passes_all_six_scenarios():
    suite = run_synthetic_evaluation_suite()
    assert suite["all_passed"] is True
    assert suite["scenario_count"] == 6
    for name, scenario in suite["scenarios"].items():
        assert scenario["passed"] is True, f"Scenario {name} failed: {scenario}"


def test_enterprise_baseline_mode_without_use_case_intake():
    pack = load_regulatory_pack()
    qbank = load_aiaf_question_bank()

    coverage = evaluate_questionnaire_coverage(
        tenant_id="tenant-enterprise",
        use_case=None,
        question_bank=qbank,
        regulatory_pack=pack,
    )
    assert set(coverage.metrics.by_authority_layer.keys()) == {
        "binding_regulatory",
        "regulatory_guidance",
        "voluntary_frameworks",
        "enterprise_internal_controls",
    }
    eu_results = [
        r for r in coverage.results if r.obligation_id.startswith("EU-AIA-")
    ]
    assert all(r.applicability.status.value == "not_applicable" for r in eu_results)

    policy_pack = extract_policy_pack(
        tenant_id="tenant-enterprise",
        name="Enterprise Baseline Policy",
        text="All AI systems must complete a privacy impact assessment.",
    )
    gaps = assess_policy_gaps(
        tenant_id="tenant-enterprise",
        use_case=None,
        policy_pack=policy_pack,
        question_bank=qbank,
        regulatory_pack=pack,
    )
    assert set(gaps.gaps_by_authority_layer.keys()) == {
        "binding_regulatory",
        "regulatory_guidance",
        "voluntary_frameworks",
        "enterprise_internal_controls",
    }


def test_private_licensed_standard_overlay_mechanism(tmp_path: Path):
    base_pack = load_regulatory_pack()
    iso_ob = next(
        ob for ob in base_pack.obligations if ob.obligation_id == "ISO42001-AIMS-ORG"
    )
    overlay_payload = {
        "sources": [],
        "obligations": [
            {
                **iso_ob.model_dump(mode="json"),
                "legal_note": "Privately licensed ISO/IEC 42001:2023 internal enterprise overlay loaded at runtime.",
            }
        ],
    }
    overlay_file = tmp_path / "private_iso_overlay.json"
    overlay_file.write_text(json.dumps(overlay_payload), encoding="utf-8")

    merged_pack = load_regulatory_pack(private_overlay_path=overlay_file)
    merged_iso = next(
        ob for ob in merged_pack.obligations if ob.obligation_id == "ISO42001-AIMS-ORG"
    )
    assert "Privately licensed ISO/IEC 42001:2023" in (merged_iso.legal_note or "")

    with pytest.raises(FileNotFoundError):
        load_regulatory_pack(private_overlay_path=tmp_path / "missing_overlay.json")

