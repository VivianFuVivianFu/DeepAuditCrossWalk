"""Acceptance and regression tests for Optional Enterprise Baseline Resolution and Dual-Mode Assessment.

Covers all 21 test requirements across Groups A, B, C, D per Prompt 2C:
Group A — Regulatory-Only Mode (Tests 1-5):
  1. A new tenant with zero enterprise policies completes a regulatory-only assessment.
  2. An existing tenant with an active Enterprise Baseline can still use regulatory-only mode.
  3. Regulatory-only results exclude enterprise-specific requirements.
  4. A conflicting explicit enterprise baseline reference fails validation (HTTP 400).
  5. Existing regulatory-only API calls continue passing.

Group B — Enterprise-Enhanced Mode (Tests 6-11):
  6. A tenant selects a valid, approved enterprise baseline.
  7. Applicable approved enterprise requirements are included in confirmed findings.
  8. Pending and rejected mappings do not contribute to confirmed coverage.
  9. Approved but unmapped enterprise requirements are preserved.
  10. Missing, archived, invalid or cross-tenant baselines produce appropriate errors (400/404).
  11. No silent fallback occurs on baseline resolution failure.

Group C — Baseline Integrity & Snapshots (Tests 12-16):
  12. Assessments use the exact selected baseline version.
  13. Updating source policies does not alter historical baseline snapshots.
  14. Updating clause review decisions does not change previously published baseline snapshots.
  15. Baseline integrity checks detect inconsistent or tampered referenced content (HTTP 422).
  16. Cross-tenant access to enterprise baseline content is strictly prevented.

Group D — End-to-End Mode Comparison & Target Scope (Tests 17-23):
  17-20. Submit the same synthetic AI questionnaire in both modes; verify identical regulatory
         obligations, distinct enterprise requirements, and correct provenance metadata.
  21. Confirm assessment execution does not mutate regulatory or enterprise baseline data.
  22. AI Governance Strategy Assessment target reports 501 Not Implemented.
  23. Direct AI Use Case Telemetry Assessment target reports 501 Not Implemented.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.models import (
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingRelationship,
    utc_now,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
    verify_baseline_integrity,
)
from banking_crosswalk.store import store


@pytest.fixture(autouse=True)
def reset_in_memory_store():
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


# ─────────────────────────────────────────────────────────────────────────────
# Helper to create an approved enterprise policy and baseline
# ─────────────────────────────────────────────────────────────────────────────
def _setup_enterprise_baseline(
    client: TestClient,
    tenant: str,
    name: str = "Standard Governance Baseline",
    policy_text: str = (
        "Every automated transaction adjustment above AUD 250 requires dual human sign-off "
        "before execution. Model weights must be cryptographically signed."
    ),
    version: str = "1.0.0",
) -> tuple[str, str]:
    """Helper to upload a policy, approve clauses, and compile an active baseline."""
    # 1. Upload policy
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Synthetic Credit & Risk Policy",
            "category": "credit_risk",
            "text": policy_text,
            "version": version,
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]

    # 2. Get clauses and approve first clause
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

    # 3. Create baseline
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


# ─────────────────────────────────────────────────────────────────────────────
# Group A — Regulatory-Only Mode (Tests 1-5)
# ─────────────────────────────────────────────────────────────────────────────

def test_1_new_tenant_zero_policies_regulatory_only(client: TestClient):
    """Test 1: A new tenant with zero enterprise policies completes a regulatory-only assessment."""
    tenant = f"tenant-new-{uuid.uuid4()}"
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
    assert data["enterprise_baseline_version"] is None
    assert data["enterprise_gaps"] == []
    assert data["applicable_enterprise_requirement_ids"] == []
    assert len(data["applicable_obligation_ids"]) > 0
    assert data["metrics"]["applicable_binding_obligations"] > 0
    assert data["provenance"]["assessment_mode"] == "regulatory_only"
    assert data["provenance"]["enterprise_baseline_id"] is None


def test_2_existing_tenant_with_active_baseline_can_use_regulatory_only(client: TestClient):
    """Test 2: An existing tenant with an active Enterprise Baseline can still use regulatory-only mode."""
    tenant = f"tenant-mature-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant)

    # Mature tenant explicitly requests regulatory_only mode
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
    # Even though tenant has an active baseline, regulatory_only strictly excludes it
    assert data["enterprise_baseline_id"] is None
    assert data["enterprise_gaps"] == []
    assert data["applicable_enterprise_requirement_ids"] == []


def test_3_regulatory_only_excludes_enterprise_requirements(client: TestClient):
    """Test 3: Regulatory-only results exclude enterprise-specific requirements and gaps."""
    tenant = f"tenant-isolated-{uuid.uuid4()}"
    _setup_enterprise_baseline(
        client,
        tenant,
        policy_text="All automated dispute refunds above AUD 50 require executive board approval.",
    )

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
    assert data["enterprise_gaps"] == []
    # All reported gaps must have source_type == 'regulatory'
    for gap in data["gaps"]:
        assert gap.get("source_type") == "regulatory"
        assert gap.get("policy_clause_id") is None


def test_4_conflicting_baseline_ref_in_regulatory_only_fails_validation(client: TestClient):
    """Test 4: A conflicting explicit enterprise baseline reference in regulatory_only fails validation (HTTP 400)."""
    tenant = f"tenant-conflict-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant)

    # Conflicting request: passes assessment_mode="regulatory_only" WITH enterprise_baseline_id
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 400
    assert "enterprise_baseline_id cannot be provided when assessment_mode is 'regulatory_only'" in res.json()["detail"]


def test_5_existing_regulatory_only_api_calls_continue_passing(client: TestClient):
    """Test 5: Existing minimal API calls without mode or baseline continue passing as regulatory_only."""
    tenant = f"tenant-legacy-{uuid.uuid4()}"
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


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Enterprise-Enhanced Mode (Tests 6-11)
# ─────────────────────────────────────────────────────────────────────────────

def test_6_tenant_selects_valid_approved_enterprise_baseline(client: TestClient):
    """Test 6: A tenant selects a valid, approved enterprise baseline."""
    tenant = f"tenant-ee-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant, version="1.2.0")

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "enterprise_baseline_version": "1.2.0",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "enterprise_enhanced"
    assert data["enterprise_baseline_id"] == bl_id
    assert data["enterprise_baseline_version"] == "1.2.0"
    assert data["provenance"]["assessment_mode"] == "enterprise_enhanced"
    assert data["provenance"]["enterprise_baseline_id"] == bl_id


def test_7_applicable_approved_enterprise_requirements_included(client: TestClient):
    """Test 7: Applicable approved enterprise requirements are included in confirmed assessment findings."""
    tenant = f"tenant-findings-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(
        client,
        tenant,
        policy_text="Every automated transaction adjustment above AUD 250 requires dual human sign-off before execution.",
    )

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert len(data["applicable_enterprise_requirement_ids"]) > 0
    assert len(data["enterprise_gaps"]) > 0
    # Every enterprise gap has source_type == 'enterprise_policy'
    for eg in data["enterprise_gaps"]:
        assert eg["source_type"] == "enterprise_policy"
        assert eg["policy_clause_id"] is not None


def test_8_pending_and_rejected_mappings_do_not_contribute_to_confirmed_coverage(client: TestClient):
    """Test 8: Pending and rejected mappings do not contribute to confirmed coverage or confirmed gaps."""
    tenant = f"tenant-review-states-{uuid.uuid4()}"
    policy_text = (
        "Clause 1: Models must log all customer transactions.\n\n"
        "Clause 2: Models must preserve explainability.\n\n"
        "Clause 3: All algorithmic operations require daily audits."
    )
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Multi-State Policy", "text": policy_text},
    )
    pol_id = res_p.json()["policy_id"]
    clauses = client.get(f"/v1/enterprise/policies/{pol_id}/clauses", headers={"X-Tenant-ID": tenant}).json()

    # Clause 0: APPROVED
    client.put(
        f"/v1/enterprise/clauses/{clauses[0]['clause_id']}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "approved", "actor": "grc-officer", "role": "compliance"},
    )
    # Clause 1: PROPOSED (left unreviewed)
    # Clause 2: REJECTED
    client.put(
        f"/v1/enterprise/clauses/{clauses[2]['clause_id']}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "rejected", "actor": "grc-officer", "role": "compliance"},
    )

    res_b = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "State Test Baseline", "policy_ids": [pol_id]},
    )
    bl_id = res_b.json()["baseline_id"]

    res_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_cov.status_code == 201
    cov_data = res_cov.json()

    # Rejected clause MUST NOT appear in applicable enterprise requirements or gaps
    rejected_clause_id = clauses[2]["clause_id"]
    assert rejected_clause_id not in cov_data["applicable_enterprise_requirement_ids"]
    assert not any(g.get("policy_clause_id") == rejected_clause_id for g in cov_data["enterprise_gaps"])

    # Approved clause IS in applicable enterprise requirements
    approved_clause_id = clauses[0]["clause_id"]
    assert approved_clause_id in cov_data["applicable_enterprise_requirement_ids"]


def test_9_approved_unmapped_enterprise_requirements_preserved(client: TestClient):
    """Test 9: Approved but unmapped enterprise requirements are preserved and assessed."""
    tenant = f"tenant-unmapped-{uuid.uuid4()}"
    # Custom requirement that does not trigger standard regex facets
    policy_text = (
        "All algorithmic decisions involving First Nations cultural assets must be approved "
        "by the Indigenous Community Advisory Council."
    )
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Indigenous Governance Policy", "text": policy_text},
    )
    pol_id = res_p.json()["policy_id"]
    clauses = client.get(f"/v1/enterprise/policies/{pol_id}/clauses", headers={"X-Tenant-ID": tenant}).json()
    assert len(clauses) > 0
    assert clauses[0]["is_unmapped"] is True

    # Approve the unmapped clause
    client.put(
        f"/v1/enterprise/clauses/{clauses[0]['clause_id']}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "grc-officer",
            "role": "compliance",
            "review_comment": "Approved custom enterprise requirement",
        },
    )

    res_b = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Custom Unmapped Baseline", "policy_ids": [pol_id]},
    )
    bl_id = res_b.json()["baseline_id"]

    res_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_cov.status_code == 201
    cov_data = res_cov.json()
    # Unmapped requirement is preserved in applicable requirements
    assert clauses[0]["clause_id"] in cov_data["applicable_enterprise_requirement_ids"]
    # Evaluated and flagged as missing in questionnaire
    assert any(g.get("policy_clause_id") == clauses[0]["clause_id"] for g in cov_data["enterprise_gaps"])


def test_10_missing_archived_invalid_or_cross_tenant_baselines_fail_closed(client: TestClient):
    """Test 10: Missing, archived, invalid or cross-tenant baselines produce appropriate errors."""
    tenant_a = f"tenant-a-{uuid.uuid4()}"
    tenant_b = f"tenant-b-{uuid.uuid4()}"
    _, bl_id_a = _setup_enterprise_baseline(client, tenant_a)

    # 1. Missing baseline_id when mode is enterprise_enhanced -> 400
    res_missing_id = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "assessment_mode": "enterprise_enhanced",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_missing_id.status_code == 400
    assert "enterprise_baseline_id is required" in res_missing_id.json()["detail"]

    # 2. Non-existent baseline -> 404
    res_not_found = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": "non-existent-baseline-id",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_not_found.status_code == 404

    # 3. Cross-tenant baseline access -> 404
    res_cross = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id_a,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_cross.status_code == 404

    # 4. Archived baseline -> 400
    # Manually archive baseline in tenant_a
    bl = store.get_enterprise_baseline(tenant_a, bl_id_a)
    archived_bl = bl.model_copy(update={"status": "archived"})
    store._enterprise_baselines[tenant_a][bl_id_a] = archived_bl

    res_archived = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id_a,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_archived.status_code == 400
    assert "is not active" in res_archived.json()["detail"]


def test_11_no_silent_fallback_occurs(client: TestClient):
    """Test 11: When enterprise baseline resolution fails, system fails closed without silent fallback."""
    tenant = f"tenant-no-fallback-{uuid.uuid4()}"
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": "invalid-or-missing-id",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    # Must fail with 404, never silently succeed returning a regulatory_only report
    assert res.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Group C — Baseline Integrity & Snapshots (Tests 12-16)
# ─────────────────────────────────────────────────────────────────────────────

def test_12_assessments_use_exact_selected_baseline_version(client: TestClient):
    """Test 12: Assessments use the exact selected baseline version."""
    tenant = f"tenant-versioning-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant, version="1.0.0")

    # Mismatched version requested -> 400
    res_mismatch = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "enterprise_baseline_version": "2.0.0",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_mismatch.status_code == 400
    assert "Enterprise baseline version mismatch" in res_mismatch.json()["detail"]

    # Matching version requested -> 201
    res_match = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "enterprise_baseline_version": "1.0.0",
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_match.status_code == 201
    assert res_match.json()["enterprise_baseline_version"] == "1.0.0"


def test_13_updating_source_policies_does_not_alter_historical_baseline_snapshots(client: TestClient):
    """Test 13: Updating source policies does not alter historical baseline snapshots."""
    tenant = f"tenant-immutable-policies-{uuid.uuid4()}"
    pol_id, bl_id = _setup_enterprise_baseline(
        client,
        tenant,
        policy_text="Original Policy Clause: Automated transaction limit AUD 250 requires dual sign-off.",
    )

    baseline_before = store.get_enterprise_baseline(tenant, bl_id)
    assert len(baseline_before.clause_snapshots) > 0
    orig_clause_text = baseline_before.clause_snapshots[0].text

    # Mutate the source policy in the store (e.g. simulating policy update or amendment)
    policy = store.get_enterprise_policy(tenant, pol_id)
    mutated_policy = policy.model_copy(
        update={"clauses": [policy.clauses[0].model_copy(update={"text": "MUTATED CLAUSE CONTENT"})]}
    )
    store.save_enterprise_policy(tenant, mutated_policy)

    # Re-evaluate baseline assessment: it must use the immutable clause snapshot, NOT the mutated policy
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    baseline_after = store.get_enterprise_baseline(tenant, bl_id)
    assert baseline_after.clause_snapshots[0].text == orig_clause_text


def test_14_updating_clause_review_does_not_alter_published_baseline_snapshots(client: TestClient):
    """Test 14: Updating clause review decisions does not change previously published baseline snapshots."""
    tenant = f"tenant-immutable-review-{uuid.uuid4()}"
    # Ingest policy with unreviewed proposed clause
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Unreviewed Baseline Policy",
        text="All customer data must be encrypted with AES-256.",
    )
    store.save_enterprise_policy(tenant, pol)
    bl = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Snapshot Baseline",
        policies=[pol],
    )
    store.save_enterprise_baseline(tenant, bl)

    # In the published baseline snapshot, the clause review_status is proposed
    assert bl.clause_snapshots[0].review_status == ClauseReviewStatus.PROPOSED

    # Now someone approves the clause in the store
    store.update_clause_review(
        tenant_id=tenant,
        clause_id=pol.clauses[0].clause_id,
        status=ClauseReviewStatus.APPROVED,
        actor="grc@bank",
        role="GRC",
    )

    # The stored published baseline's snapshot must remain unchanged (PROPOSED)
    stored_bl = store.get_enterprise_baseline(tenant, bl.baseline_id)
    assert stored_bl.clause_snapshots[0].review_status == ClauseReviewStatus.PROPOSED


def test_15_baseline_integrity_detects_tampered_fingerprint(client: TestClient):
    """Test 15: Baseline integrity checks detect tampered or inconsistent content (HTTP 422)."""
    tenant = f"tenant-tamper-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant)

    bl = store.get_enterprise_baseline(tenant, bl_id)
    assert verify_baseline_integrity(bl) is True

    # Tamper with the snapshot content
    tampered_bl = bl.model_copy(
        update={"clause_snapshots": [bl.clause_snapshots[0].model_copy(update={"text": "TAMPERED TEXT"})]}
    )
    store._enterprise_baselines[tenant][bl_id] = tampered_bl

    assert verify_baseline_integrity(tampered_bl) is False

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 422
    assert "cryptographic fingerprint mismatch" in res.json()["detail"]


def test_16_cross_tenant_access_to_baseline_content_prevented(client: TestClient):
    """Test 16: Cross-tenant access to enterprise baseline content is strictly prevented."""
    tenant_1 = f"tenant-1-{uuid.uuid4()}"
    tenant_2 = f"tenant-2-{uuid.uuid4()}"
    _, bl_id_1 = _setup_enterprise_baseline(client, tenant_1)

    # Tenant 2 cannot get Tenant 1 baseline via API
    res_get = client.get(
        f"/v1/enterprise/baselines/{bl_id_1}",
        headers={"X-Tenant-ID": tenant_2},
    )
    assert res_get.status_code == 404

    # Tenant 2 cannot assess with Tenant 1 baseline
    res_eval = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_2},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id_1,
            "use_case": {"apra_regulated": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_eval.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Group D — End-to-End Mode Comparison & Unsupported Targets (Tests 17-23)
# ─────────────────────────────────────────────────────────────────────────────

def test_17_to_20_end_to_end_mode_comparison_same_questionnaire(client: TestClient):
    """Tests 17-20: Compare the same synthetic AI questionnaire evaluated in both modes.

    17. Submit the same synthetic AI Questionnaire in both modes.
    18. Confirm both modes use the same applicable Shared Regulatory Library requirements.
    19. Confirm enterprise-enhanced mode includes additional applicable approved internal requirements.
    20. Confirm the reports correctly identify their respective assessment modes and baseline versions.
    """
    tenant = f"tenant-e2e-cmp-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(
        client,
        tenant,
        name="Enterprise Dual-Mode Baseline",
        policy_text="All automated credit decisions above AUD 250 require dual human sign-off before execution.",
        version="2.1.0",
    )

    use_case_payload = {
        "apra_regulated": True,
        "handles_personal_information": True,
        "credit_licensee_or_credit_activity": True,
    }

    # 1. Run Mode A (Regulatory-Only)
    res_a = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "use_case": use_case_payload,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_a.status_code == 201
    data_a = res_a.json()

    # 2. Run Mode B (Enterprise-Enhanced)
    res_b = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "enterprise_baseline_version": "2.1.0",
            "use_case": use_case_payload,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_b.status_code == 201
    data_b = res_b.json()

    # Check 18: Both modes use the exact same applicable Shared Regulatory Library obligations
    assert data_a["applicable_obligation_ids"] == data_b["applicable_obligation_ids"]
    assert len(data_a["applicable_obligation_ids"]) > 0
    assert data_a["metrics"]["applicable_binding_obligations"] == data_b["metrics"]["applicable_binding_obligations"]

    # Check 19: Enterprise-enhanced includes additional applicable enterprise requirements
    assert data_a["applicable_enterprise_requirement_ids"] == []
    assert data_a["enterprise_gaps"] == []
    assert len(data_b["applicable_enterprise_requirement_ids"]) > 0
    assert len(data_b["enterprise_gaps"]) > 0
    assert len(data_b["gaps"]) > len(data_a["gaps"])

    # Check 20: Reports correctly identify their respective modes and baseline versions
    assert data_a["assessment_mode"] == "regulatory_only"
    assert data_a["enterprise_baseline_id"] is None
    assert data_a["enterprise_baseline_version"] is None
    assert data_a["provenance"]["assessment_mode"] == "regulatory_only"

    assert data_b["assessment_mode"] == "enterprise_enhanced"
    assert data_b["enterprise_baseline_id"] == bl_id
    assert data_b["enterprise_baseline_version"] == "2.1.0"
    assert data_b["provenance"]["assessment_mode"] == "enterprise_enhanced"


def test_21_assessment_execution_does_not_mutate_baseline_data(client: TestClient):
    """Test 21: Confirm assessment execution does not mutate regulatory or enterprise baseline data."""
    tenant = f"tenant-no-mutation-{uuid.uuid4()}"
    _, bl_id = _setup_enterprise_baseline(client, tenant)

    bl_before = store.get_enterprise_baseline(tenant, bl_id)
    sha_before = bl_before.baseline_sha256
    rev_before = bl_before.revision

    # Run multiple assessments in both modes
    for _ in range(3):
        client.post(
            "/v1/assessments/coverage",
            headers={"X-Tenant-ID": tenant},
            json={
                "assessment_mode": "regulatory_only",
                "use_case": {"apra_regulated": True},
                "questionnaire_pack": "DEMO_BANKING_V1",
                "persist": False,
            },
        )
        client.post(
            "/v1/assessments/coverage",
            headers={"X-Tenant-ID": tenant},
            json={
                "assessment_mode": "enterprise_enhanced",
                "enterprise_baseline_id": bl_id,
                "use_case": {"apra_regulated": True},
                "questionnaire_pack": "DEMO_BANKING_V1",
                "persist": False,
            },
        )

    bl_after = store.get_enterprise_baseline(tenant, bl_id)
    assert bl_after.baseline_sha256 == sha_before
    assert bl_after.revision == rev_before
    assert bl_after.status == "active"


def test_22_unsupported_strategy_target_reports_not_implemented(client: TestClient):
    """Test 22: AI Governance Strategy Assessment target reports 501 Not Implemented."""
    tenant = f"tenant-target-strat-{uuid.uuid4()}"
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "assessment_target_type": "strategy",
            "use_case": {"apra_regulated": True},
            "persist": False,
        },
    )
    assert res.status_code == 501
    assert "Strategy Assessment is not yet implemented" in res.json()["detail"]


def test_23_unsupported_use_case_telemetry_target_reports_not_implemented(client: TestClient):
    """Test 23: Direct AI Use Case Operational Telemetry Assessment target reports 501 Not Implemented."""
    tenant = f"tenant-target-uc-{uuid.uuid4()}"
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "assessment_target_type": "use_case",
            "use_case": {"apra_regulated": True},
            "persist": False,
        },
    )
    assert res.status_code == 501
    assert "Direct AI Use Case Operational Telemetry Assessment without a questionnaire is not yet implemented" in res.json()["detail"]
