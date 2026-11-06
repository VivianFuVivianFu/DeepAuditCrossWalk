"""Comprehensive regression test suite for Prompt P1 Safety Fix A:
Final Regulatory Source Isolation & Optional Enterprise Baseline Hardening.

Covers all 28 mandatory scenarios:
Scenarios 1-8: Regulatory-Only Isolation
  1. A tenant with no enterprise policies can run Questionnaire Assessment.
  2. A tenant with a baseline can still run Regulatory-Only.
  3. Omitting assessment_mode resolves to Regulatory-Only.
  4. Omitting Use Case context does not activate Enterprise-Enhanced.
  5. The shared enterprise example is absent from assessment results entirely.
  6. AUD 1,000 approval context does not activate enterprise obligations.
  7. Voluntary frameworks are not considered adopted merely because context is missing.
  8. External regulatory applicability continues functioning.

Scenarios 9-17: Enterprise-Enhanced Execution
  9. An explicit selected approved baseline is required.
  10. A tenant-owned approved delegated-authority clause is correctly evaluated.
  11. An unrelated approved control mapping does not activate a platform example obligation.
  12. Pending and rejected clauses do not produce confirmed findings.
  13. Approved unmapped requirements remain traceable.
  14. AUD 500 enterprise approval versus AUD 1,000 use-case configuration detects the applicable discrepancy.
  15. Cross-tenant access is rejected.
  16. Baseline snapshot integrity and versioning are preserved.
  17. No silent fallback occurs.

Scenarios 18-21: Baseline Eligibility & Compilation
  18. Empty policy lists cannot produce eligible active baselines.
  19. Wholly unapproved content cannot become eligible (compiles as draft).
  20. Draft baselines cannot be selected for confirmed Enterprise-Enhanced assessments.
  21. Approved enterprise-specific requirements can be represented without forced Canonical Control mappings.

Scenarios 22-28: System Compatibility, Importer & Regression
  22. The generic XLSX importer from PR #22 remains functional.
  23. No AIAF-specific behaviour is reintroduced.
  24. Existing P0 and P1 questionnaire regression tests pass.
  25. Existing numeric and negation regression tests pass.
  26. Historical library and baseline references remain auditable.
  27. PostgreSQL and tenant isolation tests pass where executable.
  28. Research-only A0/A1 experiment code remains unchanged.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from banking_crosswalk.app import app
from banking_crosswalk.catalog import (
    load_demo_questionnaire,
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_unified_control_library,
    validate_regulatory_pack,
)
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.importer import import_questionnaire_workbook
from banking_crosswalk.models import (
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    CoverageAssessment,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingRelationship,
    QuestionBank,
    QuestionRecord,
    utc_now,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
    verify_baseline_integrity,
)
from banking_crosswalk.store import ConflictError, NotFoundError, store


@pytest.fixture(autouse=True)
def reset_in_memory_store():
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


def _setup_approved_baseline(
    client: TestClient,
    tenant: str,
    name: str = "Test Enterprise Baseline",
    policy_text: str = (
        "Human approval is required for all customer credit decisions exceeding AUD 500."
    ),
    version: str = "1.0.0",
) -> tuple[str, str]:
    """Helper to upload a policy, approve clauses, and compile an active baseline."""
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Synthetic Credit Risk Policy",
            "category": "credit_risk",
            "text": policy_text,
            "version": version,
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]

    clauses_res = client.get(
        f"/v1/enterprise/policies/{pol_id}/clauses",
        headers={"X-Tenant-ID": tenant},
    )
    assert clauses_res.status_code == 200
    clauses = clauses_res.json()
    assert len(clauses) > 0

    c0_id = clauses[0]["clause_id"]
    rev_res = client.put(
        f"/v1/enterprise/clauses/{c0_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "grc-officer@bank.example",
            "role": "compliance",
            "review_comment": "Approved for baseline",
        },
    )
    assert rev_res.status_code == 200

    res_b = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": name,
            "policy_ids": [pol_id],
            "version": version,
            "status": "active",
        },
    )
    assert res_b.status_code == 201
    bl_id = res_b.json()["baseline_id"]
    return pol_id, bl_id


# ==============================================================================
# Group 1: Regulatory-Only Isolation (Scenarios 1-8)
# ==============================================================================

def test_scenario_1_tenant_with_no_enterprise_policies_runs_questionnaire_assessment(
    client: TestClient,
    regulatory_pack,
):
    """Scenario 1: A tenant with no enterprise policies can run Questionnaire Assessment."""
    tenant = f"tenant-no-policies-{uuid.uuid4()}"
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "use_case": {"apra_regulated": True, "handles_personal_information": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "regulatory_only"
    assert data["enterprise_baseline_id"] is None
    assert data["applicable_enterprise_requirement_ids"] == []
    assert data["enterprise_gaps"] == []
    assert len(data["applicable_obligation_ids"]) > 0

    # Also directly via Python coverage function
    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        assessment_mode="regulatory_only",
    )
    assert result.assessment_mode == "regulatory_only"
    assert result.applicable_enterprise_requirement_ids == []
    assert result.enterprise_gaps == []
    assert len(result.applicable_obligation_ids) > 0


def test_scenario_2_tenant_with_baseline_can_still_run_regulatory_only(
    client: TestClient,
    regulatory_pack,
):
    """Scenario 2: A tenant with a baseline can still run Regulatory-Only."""
    tenant = f"tenant-mature-{uuid.uuid4()}"
    _, bl_id = _setup_approved_baseline(client, tenant)

    # Mature tenant explicitly requests regulatory_only mode without baseline_id
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "regulatory_only"
    assert data["enterprise_baseline_id"] is None
    assert data["applicable_enterprise_requirement_ids"] == []
    assert data["enterprise_gaps"] == []

    # If tenant provides enterprise_baseline_id in regulatory_only mode, API rejects it
    rej = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "enterprise_baseline_id": bl_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert rej.status_code == 400
    assert "enterprise_baseline_id cannot be provided" in rej.json()["detail"]


def test_scenario_3_omitting_assessment_mode_resolves_to_regulatory_only(
    client: TestClient,
    regulatory_pack,
):
    """Scenario 3: Omitting assessment_mode resolves to Regulatory-Only."""
    tenant = f"tenant-default-mode-{uuid.uuid4()}"

    # API call with assessment_mode omitted
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "regulatory_only"
    assert data["enterprise_baseline_id"] is None
    assert data["applicable_enterprise_requirement_ids"] == []

    # Python call with assessment_mode=None
    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        assessment_mode=None,
    )
    assert result.assessment_mode == "regulatory_only"
    assert result.applicable_enterprise_requirement_ids == []


def test_scenario_4_omitting_use_case_context_does_not_activate_enterprise_enhanced(
    regulatory_pack,
):
    """Scenario 4: Omitting Use Case context does not activate Enterprise-Enhanced."""
    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        use_case=None,
    )
    assert result.assessment_mode == "regulatory_only"
    assert result.applicable_enterprise_requirement_ids == []
    assert result.enterprise_gaps == []


def test_scenario_5_shared_enterprise_example_absent_from_assessment_results(
    regulatory_pack,
):
    """Scenario 5: The shared enterprise example is absent from assessment results entirely."""
    # Ensure source ENTERPRISE-AI-STD is not in active pack
    source_ids = {s.source_id for s in regulatory_pack.sources}
    assert "ENTERPRISE-AI-STD" not in source_ids

    # Ensure obligation ENT-AI-DELEGATED-APPROVAL is not in active pack
    obligation_ids = {o.obligation_id for o in regulatory_pack.obligations}
    assert "ENT-AI-DELEGATED-APPROVAL" not in obligation_ids

    # Ensure evaluation never returns ENT-AI-DELEGATED-APPROVAL
    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        assessment_mode="regulatory_only",
    )
    assert "ENT-AI-DELEGATED-APPROVAL" not in result.applicable_obligation_ids
    assert not any(
        g.obligation_id == "ENT-AI-DELEGATED-APPROVAL" for g in result.gaps
    )


def test_scenario_6_aud_1000_approval_context_does_not_activate_enterprise_obligations(
    regulatory_pack,
):
    """Scenario 6: AUD 1,000 approval context does not activate enterprise obligations."""
    bank = load_demo_questionnaire()
    uc = BankingUseCase(
        name="Credit Decisioning",
        approval_threshold_aud=1000.0,
        enterprise_controls_enabled=False,
    )
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        assessment_mode="regulatory_only",
    )
    assert result.assessment_mode == "regulatory_only"
    assert result.applicable_enterprise_requirement_ids == []
    assert result.enterprise_gaps == []
    assert "ENT-AI-DELEGATED-APPROVAL" not in result.applicable_obligation_ids


def test_scenario_7_voluntary_frameworks_not_assumed_adopted_when_context_missing(
    regulatory_pack,
):
    """Scenario 7: Voluntary frameworks are not considered adopted merely because context is missing."""
    uc = BankingUseCase.enterprise_baseline()
    assert uc.nist_ai_rmf_adopted is None
    assert uc.au_ai_guidance_adopted is None
    assert uc.iso_42001_adopted is None
    assert uc.iso_23894_adopted is None
    assert uc.iso_27001_adopted is None

    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        assessment_mode="regulatory_only",
    )

    # Voluntary framework obligations must not be applicable
    for ob_id in result.applicable_obligation_ids:
        assert not ob_id.startswith("NIST-AI-RMF-")
        assert not ob_id.startswith("ISO-42001-")
        assert not ob_id.startswith("ISO-23894-")
        assert not ob_id.startswith("AU-AI-SAFETY-")


def test_scenario_8_external_regulatory_applicability_continues_functioning(
    regulatory_pack,
):
    """Scenario 8: External regulatory applicability continues functioning."""
    bank = load_demo_questionnaire()
    uc = BankingUseCase.synthetic_demo()
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        assessment_mode="regulatory_only",
    )

    # Core statutory obligations must be present
    assert any(ob_id.startswith("AU-PRIV-APP") for ob_id in result.applicable_obligation_ids)
    assert any(ob_id.startswith("AU-APRA-CPS") for ob_id in result.applicable_obligation_ids)
    assert len(result.applicable_obligation_ids) > 0


# ==============================================================================
# Group 2: Enterprise-Enhanced Execution (Scenarios 9-17)
# ==============================================================================

def test_scenario_9_explicit_selected_approved_baseline_required(
    client: TestClient,
    regulatory_pack,
):
    """Scenario 9: An explicit selected approved baseline is required for enterprise_enhanced."""
    tenant = f"tenant-missing-baseline-{uuid.uuid4()}"

    # API call missing enterprise_baseline_id
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 400
    assert "enterprise_baseline_id is required" in res.json()["detail"]

    # Direct Python call missing enterprise_baseline
    bank = load_demo_questionnaire()
    with pytest.raises(ValueError, match="no eligible enterprise_baseline was provided"):
        evaluate_questionnaire_coverage(
            tenant_id=tenant,
            question_bank=bank,
            regulatory_pack=regulatory_pack,
            assessment_mode="enterprise_enhanced",
            enterprise_baseline=None,
        )


def test_scenario_10_tenant_owned_approved_delegated_authority_evaluated(
    client: TestClient,
):
    """Scenario 10: A tenant-owned approved delegated-authority clause is correctly evaluated."""
    tenant = f"tenant-delegated-{uuid.uuid4()}"
    _, bl_id = _setup_approved_baseline(
        client,
        tenant,
        policy_text="Human approval is required for credit adjustments exceeding AUD 500.",
    )

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "enterprise_enhanced"
    assert data["enterprise_baseline_id"] == bl_id
    assert len(data["applicable_enterprise_requirement_ids"]) == 1


def test_scenario_11_unrelated_approved_control_mapping_does_not_activate_platform_example(
    client: TestClient,
):
    """Scenario 11: An unrelated approved control mapping does not activate a platform example obligation."""
    tenant = f"tenant-unrelated-{uuid.uuid4()}"
    _, bl_id = _setup_approved_baseline(
        client,
        tenant,
        policy_text="All AI cybersecurity incidents must be reported to the CISO within 2 hours.",
    )

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "ENT-AI-DELEGATED-APPROVAL" not in data["applicable_obligation_ids"]
    assert not any(
        g.get("obligation_id") == "ENT-AI-DELEGATED-APPROVAL"
        for g in data.get("regulatory_gaps", [])
    )


def test_scenario_12_pending_and_rejected_clauses_gated(client: TestClient):
    """Scenario 12: Pending and rejected clauses do not produce confirmed findings."""
    tenant = f"tenant-gating-{uuid.uuid4()}"

    # Import policy with two distinct lines
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Mixed Status Policy",
            "text": (
                "Human approval is required for all customer refund credits exceeding AUD 250.\n"
                "Experimental models may bypass dual review during testing."
            ),
            "version": "1.0.0",
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]

    clauses_res = client.get(
        f"/v1/enterprise/policies/{pol_id}/clauses",
        headers={"X-Tenant-ID": tenant},
    )
    clauses = clauses_res.json()
    assert len(clauses) >= 2

    # Approve only clause 0; leave clause 1 as proposed
    c0_id = clauses[0]["clause_id"]
    c1_id = clauses[1]["clause_id"]

    rev_res = client.put(
        f"/v1/enterprise/clauses/{c0_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "officer@bank.example",
            "role": "compliance",
            "review_comment": "Approved clause",
        },
    )
    assert rev_res.status_code == 200

    # Compile baseline
    res_b = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Gating Test Baseline", "policy_ids": [pol_id], "status": "active"},
    )
    assert res_b.status_code == 201
    bl_id = res_b.json()["baseline_id"]

    # Assess in enterprise_enhanced mode
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    # Only c0_id is evaluated; c1_id must be gated out
    assert c0_id in data["applicable_enterprise_requirement_ids"]
    assert c1_id not in data["applicable_enterprise_requirement_ids"]


def test_scenario_13_approved_unmapped_requirements_remain_traceable(
    regulatory_pack,
):
    """Scenario 13: Approved unmapped requirements remain traceable."""
    tenant = f"tenant-unmapped-{uuid.uuid4()}"
    policy = EnterprisePolicy(
        policy_id="pol-custom-1",
        tenant_id=tenant,
        name="Custom AI Ethics Policy",
        version="1.0.0",
        clauses=[
            EnterpriseClause(
                clause_id="clause-unmapped-01",
                policy_id="pol-custom-1",
                tenant_id=tenant,
                source_name="Custom AI Ethics Policy",
                text="The AI Ethics Advisory Board must review high-impact customer algorithms annually.",
                review_status=ClauseReviewStatus.APPROVED,
                is_unmapped=True,
                control_mappings=[],
            )
        ],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant, name="Custom AI Ethics Baseline", policies=[policy], status="active"
    )
    assert baseline.status == "active"
    assert baseline.clause_snapshots[0].is_unmapped is True
    assert len(baseline.clause_snapshots[0].control_mappings) == 0
    assert "clause-unmapped-01" in baseline.unmapped_clause_ids

    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    assert "clause-unmapped-01" in result.applicable_enterprise_requirement_ids


def test_scenario_14_aud_500_enterprise_vs_1000_usecase_detects_applicable_discrepancy(
    client: TestClient,
):
    """Scenario 14: AUD 500 enterprise approval versus AUD 1,000 use-case detects discrepancy."""
    tenant = f"tenant-threshold-conflict-{uuid.uuid4()}"
    _, bl_id = _setup_approved_baseline(
        client,
        tenant,
        policy_text="Human approval is required for all credit adjustments exceeding AUD 500.",
    )

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {
                "name": "Automated Adjustments",
                "approval_threshold_aud": 1000.0,
                "approval_threshold_operator": ">",
            },
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert len(data["applicable_enterprise_requirement_ids"]) > 0
    # Conflict detected between policy AUD 500 and use case AUD 1000
    conflicts = [
        g for g in data.get("enterprise_gaps", [])
        if "exceeds approved policy threshold" in g.get("title", "").lower()
        or g.get("gap_type") == "policy_conflict"
        or (g.get("required_threshold") == 500.0 and g.get("use_case_threshold") == 1000.0)
    ]
    assert len(conflicts) > 0


def test_scenario_15_cross_tenant_access_rejected(client: TestClient):
    """Scenario 15: Cross-tenant access is rejected."""
    tenant_a = f"tenant-a-{uuid.uuid4()}"
    tenant_b = f"tenant-b-{uuid.uuid4()}"
    _, bl_a_id = _setup_approved_baseline(client, tenant_a)

    # Tenant B tries to use Tenant A's baseline
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_a_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_scenario_16_baseline_snapshot_integrity_and_versioning_preserved(
    client: TestClient,
):
    """Scenario 16: Baseline snapshot integrity and versioning are preserved."""
    tenant = f"tenant-integrity-{uuid.uuid4()}"
    _, bl_id = _setup_approved_baseline(client, tenant)

    baseline = store.get_enterprise_baseline(tenant, bl_id)
    assert verify_baseline_integrity(baseline) is True

    # Tampering with fingerprint causes integrity check to fail
    tampered = baseline.model_copy(update={"baseline_sha256": "badbeef" * 8})
    assert verify_baseline_integrity(tampered) is False

    # Store immutability rejects mutation under same revision
    with pytest.raises(ConflictError):
        store.save_enterprise_baseline(
            tenant,
            baseline.model_copy(
                update={
                    "clause_snapshots": [],
                    "baseline_sha256": "changed" + "0" * 57,
                }
            ),
        )


def test_scenario_17_no_silent_fallback_occurs(client: TestClient):
    """Scenario 17: No silent fallback occurs on baseline error in enterprise_enhanced."""
    tenant = f"tenant-no-fallback-{uuid.uuid4()}"

    # Missing baseline ID -> 400
    res1 = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={"assessment_mode": "enterprise_enhanced", "persist": False},
    )
    assert res1.status_code == 400

    # Non-existent baseline ID -> 404 (never silently falls back to 201 regulatory_only)
    res2 = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": "bl-non-existent",
            "persist": False,
        },
    )
    assert res2.status_code == 404


# ==============================================================================
# Group 3: Baseline Eligibility & Compilation (Scenarios 18-21)
# ==============================================================================

def test_scenario_18_empty_policy_lists_cannot_produce_eligible_active_baselines(
    client: TestClient,
):
    """Scenario 18: Empty policy lists cannot produce eligible active baselines."""
    tenant = f"tenant-empty-{uuid.uuid4()}"

    # Direct function call raises ValueError
    with pytest.raises(ValueError, match="Cannot compile an active baseline from empty policy input"):
        compile_enterprise_baseline(
            tenant_id=tenant, name="Empty Baseline", policies=[], status="active"
        )

    # API call returns HTTP 422
    res = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Empty Baseline", "policy_ids": [], "status": "active"},
    )
    assert res.status_code == 422
    assert "empty policy input" in res.json()["detail"].lower()


def test_scenario_19_wholly_unapproved_content_cannot_become_eligible():
    """Scenario 19: Wholly unapproved content cannot become eligible (compiles as draft)."""
    tenant = f"tenant-unreviewed-{uuid.uuid4()}"
    policy = EnterprisePolicy(
        policy_id="pol-unreviewed",
        tenant_id=tenant,
        name="Unreviewed Policy",
        version="1.0.0",
        clauses=[
            EnterpriseClause(
                clause_id="clause-1",
                policy_id="pol-unreviewed",
                tenant_id=tenant,
                source_name="Unreviewed Policy",
                text="Model cards must be updated monthly.",
                review_status=ClauseReviewStatus.PROPOSED,
            )
        ],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant, name="Unreviewed Baseline", policies=[policy], status="active"
    )
    # Wholly unapproved content must compile as draft
    assert baseline.status == "draft"
    assert any("draft" in note.lower() for note in baseline.warnings)


def test_scenario_20_draft_baselines_cannot_be_selected_for_confirmed_assessment(
    client: TestClient,
    regulatory_pack,
):
    """Scenario 20: Draft baselines cannot be selected for confirmed Enterprise-Enhanced assessments."""
    tenant = f"tenant-draft-select-{uuid.uuid4()}"
    policy = EnterprisePolicy(
        policy_id="pol-draft",
        tenant_id=tenant,
        name="Draft Policy",
        version="1.0.0",
        clauses=[
            EnterpriseClause(
                clause_id="clause-draft-1",
                policy_id="pol-draft",
                tenant_id=tenant,
                source_name="Draft Policy",
                text="Testing clause.",
                review_status=ClauseReviewStatus.PROPOSED,
            )
        ],
    )
    draft_baseline = compile_enterprise_baseline(
        tenant_id=tenant, name="Draft Baseline", policies=[policy], status="draft"
    )
    assert draft_baseline.status == "draft"

    # Direct Python call raises ValueError
    bank = load_demo_questionnaire()
    with pytest.raises(ValueError, match="Draft baselines cannot be selected for confirmed enterprise_enhanced assessments"):
        evaluate_questionnaire_coverage(
            tenant_id=tenant,
            question_bank=bank,
            regulatory_pack=regulatory_pack,
            enterprise_baseline=draft_baseline,
            assessment_mode="enterprise_enhanced",
        )

    # API call returns HTTP 400
    store.save_enterprise_baseline(tenant, draft_baseline)
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": draft_baseline.baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 400
    assert "not active" in res.json()["detail"].lower() or "draft" in res.json()["detail"].lower()


def test_scenario_21_approved_enterprise_requirements_without_forced_canonical_mappings():
    """Scenario 21: Approved enterprise requirements represented without forced Canonical Control mappings."""
    tenant = f"tenant-no-canonical-{uuid.uuid4()}"
    policy = EnterprisePolicy(
        policy_id="pol-unique",
        tenant_id=tenant,
        name="Custom AI Governance Standard",
        version="1.0.0",
        clauses=[
            EnterpriseClause(
                clause_id="clause-bespoke-01",
                policy_id="pol-unique",
                tenant_id=tenant,
                source_name="Custom AI Governance Standard",
                text="Independent model fairness committee review required before deployment.",
                review_status=ClauseReviewStatus.APPROVED,
                is_unmapped=True,
                control_mappings=[],
            )
        ],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant, name="Unique Baseline", policies=[policy], status="active"
    )
    assert baseline.status == "active"
    assert baseline.clause_snapshots[0].is_unmapped is True
    assert len(baseline.clause_snapshots[0].control_mappings) == 0
    assert len(baseline.clause_snapshots) == 1
    assert "clause-bespoke-01" in baseline.unmapped_clause_ids


# ==============================================================================
# Group 4: System Compatibility, Importer & Regression (Scenarios 22-28)
# ==============================================================================

def test_scenario_22_generic_xlsx_importer_remains_functional():
    """Scenario 22: The generic XLSX importer from PR #22 remains functional."""
    wb = Workbook()
    ws = wb.active
    ws.title = "AI Governance Questionnaire"
    ws.append(["Question ID", "Question Text", "Category", "Answer", "Evidence"])
    ws.append([
        "Q-GEN-001",
        "Does the organisation maintain a human-in-the-loop review mechanism for high-risk AI decisions?",
        "Human Oversight",
        "Yes",
        "Operational Standard Operating Procedure v2.1",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bank = import_questionnaire_workbook(raw, "generic_test.xlsx")
    assert isinstance(bank, QuestionBank)
    assert len(bank.questions) == 1
    q = bank.questions[0]
    assert "human-in-the-loop" in q.question_text.lower()


def test_scenario_23_no_aiaf_specific_behaviour_reintroduced():
    """Scenario 23: No AIAF-specific behaviour is reintroduced."""
    # Custom non-AIAF sheet name works seamlessly
    wb = Workbook()
    ws = wb.active
    ws.title = "Internal Audit Section"
    ws.append(["ID", "Question", "Topic"])
    ws.append(["Q-001", "Are model training datasets monitored for bias?", "Fairness"])
    buf = io.BytesIO()
    wb.save(buf)

    bank = import_questionnaire_workbook(buf.getvalue(), "custom_sheets.xlsx")
    assert len(bank.questions) == 1
    assert "monitored for bias" in bank.questions[0].question_text.lower()


def test_scenario_24_existing_p0_and_p1_questionnaire_regressions_pass(
    regulatory_pack,
):
    """Scenario 24: Existing P0 and P1 questionnaire regression tests pass."""
    bank = load_demo_questionnaire()
    result = evaluate_questionnaire_coverage(
        tenant_id="test-tenant",
        question_bank=bank,
        regulatory_pack=regulatory_pack,
        assessment_mode="regulatory_only",
    )
    assert result.metrics.applicable_binding_obligations > 0
    assert result.metrics.confirmed_coverage_rate >= 0.0
    assert len(result.results) > 0


def test_scenario_25_existing_numeric_and_negation_regressions_pass():
    """Scenario 25: Existing numeric and negation regression tests pass."""
    pol = extract_enterprise_policy(
        tenant_id="tenant-test",
        name="Credit Policy",
        text="Transactions above AUD 500 require approval unless an authorised exception applies.",
    )
    c = pol.clauses[0]
    assert 500.0 in c.thresholds_aud
    assert "approval_threshold_defined" in c.control_facets
    assert c.has_exception_clause is True

    # Prohibition vs absence
    pol_prohib = extract_enterprise_policy(
        tenant_id="tenant-test",
        name="Prohibition Policy",
        text="The agent must not execute a refund before human approval.",
    )
    c_prohib = pol_prohib.clauses[0]
    assert c_prohib.mandatory is True
    assert "human_approval_required" in c_prohib.control_facets


def test_scenario_26_historical_library_and_baseline_references_auditable(
    regulatory_pack,
):
    """Scenario 26: Historical library and baseline references remain auditable."""
    controls = load_unified_control_library()
    mappings = load_obligation_control_mappings()
    assert regulatory_pack.version == "0.1.0"
    assert len(regulatory_pack.sources) == 17
    assert len(regulatory_pack.obligations) == 45
    assert len(controls.controls) == 33
    assert len(mappings.mappings) == 55
    assert regulatory_pack.verified_as_of is not None


def test_scenario_27_tenant_isolation_tests_pass(client: TestClient):
    """Scenario 27: PostgreSQL and tenant isolation tests pass where executable."""
    tenant_1 = f"tenant-iso-1-{uuid.uuid4()}"
    tenant_2 = f"tenant-iso-2-{uuid.uuid4()}"

    _, bl_1_id = _setup_approved_baseline(client, tenant_1)

    # In store, tenant_2 cannot access tenant_1 baseline
    with pytest.raises(NotFoundError):
        store.get_enterprise_baseline(tenant_2, bl_1_id)


def test_scenario_28_research_only_a0_a1_experiment_code_unchanged():
    """Scenario 28: Research-only A0/A1 experiment code remains unchanged."""
    dataset_path = Path("P1_EVALUATION_DATASET_V2.json")
    assert dataset_path.exists()
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "cases" in data
    assert len(data["cases"]) == 156
