"""Automated Baseline Integrity Tests for DeepAudit Crosswalk Enterprise Policy Layer.

Covers the complete baseline-building workflow:
Enterprise Policy Upload -> Clause Extraction -> Atomic Enterprise Requirements ->
Candidate Unified Control Mapping -> Human Review -> Versioned Enterprise Baseline.

Exercises all 10 integrity requirements:
1. Uploading one policy (clauses extracted, candidate mappings proposed, no unintended assessment).
2. Uploading multiple policies (independent ingestion & baseline aggregation).
3. Duplicate policy requirements (deduplication warning detection).
4. Conflicting internal requirements (internal threshold conflicts detected without declaring statutory breaches).
5. Superseded policy versions (warning on superseded/retired policies).
6. Missing Unified Control mappings (unmapped requirements preserved, not silently dropped).
7. Proposed, approved, and rejected mapping states (only approved mappings contribute to confirmed baseline controls).
8. Baseline version creation and immutability (cryptographic fingerprint, revision tracking, immutability check).
9. Cross-tenant access attempts (strict tenant isolation on policies, clauses, and baselines).
10. Source and audit traceability (document provenance, reviewer identity, audit trail events).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    GapType,
)
from banking_crosswalk.policy import (
    assess_enterprise_policy_gaps,
    compile_enterprise_baseline,
    extract_enterprise_policy,
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


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Uploading one policy
# ─────────────────────────────────────────────────────────────────────────────
def test_1_upload_single_policy(client):
    tenant = f"tenant-single-{uuid.uuid4()}"
    policy_text = (
        "All automated customer refund transactions exceeding AUD 500 must require "
        "human manager sign-off prior to execution."
    )
    res = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Refund Delegated Authority Standard",
            "text": policy_text,
            "version": "1.0.0",
            "category": "delegated_authority",
            "authority_level": "enterprise_policy",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Refund Delegated Authority Standard"
    assert data["version"] == "1.0.0"
    assert len(data["clauses"]) > 0

    clause = data["clauses"][0]
    assert clause["mandatory"] is True
    assert 500.0 in clause["thresholds_aud"]
    assert "human_approval_required" in clause["control_facets"]
    assert "pre_execution_block" in clause["control_facets"]
    assert clause["review_status"] == "proposed"

    # Candidate mapping to Unified Control is proposed, not confirmed
    mappings = clause["control_mappings"]
    assert len(mappings) > 0
    assert any(m["control_id"] == "CTRL-FIN-APPROVAL-THRESHOLDS" for m in mappings)
    assert all(m["review_status"] == "proposed" for m in mappings)

    # Policy import must not create any downstream assessment records
    assert len(store._assessments.get(tenant, {})) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Uploading multiple policies
# ─────────────────────────────────────────────────────────────────────────────
def test_2_upload_multiple_policies(client):
    tenant = f"tenant-multi-{uuid.uuid4()}"

    # Policy 1: Financial delegated authority
    res1 = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Refund Operations Policy",
            "text": "Refunds above AUD 500 require authorised officer approval before payment.",
            "category": "credit_ops",
        },
    )
    assert res1.status_code == 201
    pol1_id = res1.json()["policy_id"]

    # Policy 2: Biometric privacy standard
    res2 = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Biometric Privacy Standard",
            "text": "Customer consent must be recorded prior to collecting sensitive biometrics.",
            "category": "privacy",
        },
    )
    assert res2.status_code == 201
    pol2_id = res2.json()["policy_id"]

    # Compile baseline containing both policies
    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Banking Operations & Privacy Baseline",
            "description": "Baseline combining financial operations and privacy standards",
            "policy_ids": [pol1_id, pol2_id],
            "version": "1.0.0",
        },
    )
    assert res_bl.status_code == 201
    bl_data = res_bl.json()
    assert set(bl_data["policy_ids"]) == {pol1_id, pol2_id}
    assert bl_data["version"] == "1.0.0"
    assert bl_data["revision"] == 1
    assert bl_data["baseline_sha256"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Duplicate policy requirements
# ─────────────────────────────────────────────────────────────────────────────
def test_3_duplicate_policy_requirements():
    tenant = f"tenant-dup-{uuid.uuid4()}"
    duplicate_clause = "Dual authorised officer sign-off is mandatory for all high-risk AI deployments."

    pol1 = extract_enterprise_policy(
        tenant_id=tenant,
        name="AI Risk Standard",
        text=duplicate_clause,
        version="1.0.0",
    )
    pol2 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Credit Systems Policy",
        text=duplicate_clause,
        version="1.0.0",
    )

    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Deduplicated Baseline",
        policies=[pol1, pol2],
    )

    # Detects and records deduplication warning without failing compilation
    assert len(baseline.warnings) > 0
    assert any("Duplicate requirement detected" in w for w in baseline.warnings)
    # Both clauses are preserved for audit traceability
    all_clauses = [c for p in [pol1, pol2] for c in p.clauses]
    assert len(all_clauses) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Conflicting internal requirements
# ─────────────────────────────────────────────────────────────────────────────
def test_4_conflicting_internal_requirements(regulatory_pack):
    tenant = f"tenant-conflict-{uuid.uuid4()}"
    pol_credit = extract_enterprise_policy(
        tenant_id=tenant,
        name="Credit Card Policy",
        text="All customer refund credits above AUD 1,000 require manual manager sign-off.",
        category="credit",
    )
    pol_fraud = extract_enterprise_policy(
        tenant_id=tenant,
        name="Fraud Operations Policy",
        text="All automated dispute credits above AUD 500 must be reviewed and approved by human supervisor.",
        category="fraud",
    )

    # Baseline compilation detects internal conflict
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Consolidated Operations Baseline",
        policies=[pol_credit, pol_fraud],
    )

    assert len(baseline.conflicts) > 0
    conflict = baseline.conflicts[0]
    assert conflict.gap_type == GapType.CONTROL_CONFLICT
    assert "conflicting AUD approval thresholds" in conflict.title
    assert conflict.severity == "high"

    # CRITICAL: Verify this internal inconsistency does NOT declare statutory non-compliance
    # for external regulations (no spurious APRA CPS 234 / Privacy Act breaches)
    from banking_crosswalk.catalog import load_aiaf_question_bank
    qbank = load_aiaf_question_bank()

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[pol_credit, pol_fraud],
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
    )
    # The conflict is reported as an internal CONTROL_CONFLICT
    assert len(assessment.control_conflicts) > 0
    # No spurious statutory breaches for unaddressed domains (e.g. ASIC RG 271, Privacy Act)
    rg271_gaps = [
        g for g in assessment.policy_gaps
        if g.obligation_id and "RG271" in g.obligation_id
    ]
    assert len(rg271_gaps) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Superseded policy versions
# ─────────────────────────────────────────────────────────────────────────────
def test_5_superseded_policy_versions():
    tenant = f"tenant-superseded-{uuid.uuid4()}"
    pol_old = extract_enterprise_policy(
        tenant_id=tenant,
        name="Fraud Dispute Policy",
        text="All refunds above AUD 1,000 require manager approval.",
        version="1.0.0",
    )
    pol_old.status = "superseded"

    pol_new = extract_enterprise_policy(
        tenant_id=tenant,
        name="Fraud Dispute Policy",
        text="All refunds above AUD 500 require manager approval.",
        version="2.0.0",
    )
    pol_new.status = "active"

    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Fraud Policy Baseline",
        policies=[pol_old, pol_new],
    )

    assert len(baseline.warnings) > 0
    # Detects both superseded status and multiple versions of the same policy
    assert any("superseded" in w.lower() for w in baseline.warnings)
    assert any("Multiple versions" in w for w in baseline.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Missing Unified Control mappings (Unmapped Requirements Preserved)
# ─────────────────────────────────────────────────────────────────────────────
def test_6_unmapped_enterprise_requirements_preserved():
    tenant = f"tenant-unmapped-{uuid.uuid4()}"
    custom_policy_text = (
        "Indigenous data sovereignty protocols and consultation with First Nations community "
        "representatives must precede training on regional acoustic dialect datasets."
    )
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Community AI Ethics Standard",
        text=custom_policy_text,
    )

    assert len(pol.clauses) > 0
    clause = pol.clauses[0]
    # Clause has no matching Unified Control and must not falsely trigger cross-border privacy
    assert clause.is_unmapped is True
    assert len(clause.control_mappings) == 0

    # Compile into baseline
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Community AI Baseline",
        policies=[pol],
    )

    # Preserved in unmapped_clause_ids, not silently dropped
    assert clause.clause_id in baseline.unmapped_clause_ids
    assert len(baseline.confirmed_control_ids) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Proposed, approved, and rejected mapping states
# ─────────────────────────────────────────────────────────────────────────────
def test_7_mapping_review_states_workflow(client):
    tenant = f"tenant-workflow-{uuid.uuid4()}"
    policy_text = (
        "All refunds above AUD 500 require human manager approval before payment.\n\n"
        "All user prompts sent to third-party LLMs must undergo prompt logging and telemetry.\n\n"
        "Algorithmic bias testing across protected attributes is mandatory quarterly."
    )
    res = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Comprehensive AI Standard",
            "text": policy_text,
        },
    )
    assert res.status_code == 201
    pol_id = res.json()["policy_id"]

    clauses_res = client.get(
        f"/v1/enterprise/policies/{pol_id}/clauses",
        headers={"X-Tenant-ID": tenant},
    )
    assert clauses_res.status_code == 200
    clauses = clauses_res.json()
    assert len(clauses) >= 3

    # Initial state: all proposed
    assert all(c["review_status"] == "proposed" for c in clauses)

    # 1. Approve Clause 0 (refund approval) and independently approve its control mappings
    c0_id = clauses[0]["clause_id"]
    rev0 = client.put(
        f"/v1/enterprise/clauses/{c0_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "lead-compliance-officer",
            "role": "compliance",
            "review_comment": "Verified against Delegated Authority Schedule",
        },
    )
    assert rev0.status_code == 200
    assert rev0.json()["review_status"] == "approved"
    # Clause approval does not implicitly approve control mappings; approve them explicitly
    for m in rev0.json()["control_mappings"]:
        rev_m = client.put(
            f"/v1/enterprise/clauses/{c0_id}/mappings/{m['mapping_id']}/review",
            headers={"X-Tenant-ID": tenant},
            json={
                "status": "approved",
                "actor": "lead-compliance-officer",
                "role": "compliance",
                "review_comment": "Verified control mapping equivalence",
            },
        )
        assert rev_m.status_code == 200

    # 2. Reject Clause 1 (prompt logging)
    c1_id = clauses[1]["clause_id"]
    rev1 = client.put(
        f"/v1/enterprise/clauses/{c1_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "rejected",
            "actor": "lead-compliance-officer",
            "role": "compliance",
            "review_comment": "Telemetry requirements already covered by InfoSec policy",
        },
    )
    assert rev1.status_code == 200
    assert rev1.json()["review_status"] == "rejected"

    # 3. Leave Clause 2 as proposed (bias testing)

    # Compile baseline
    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Reviewed Baseline",
            "policy_ids": [pol_id],
        },
    )
    assert res_bl.status_code == 201
    bl = res_bl.json()

    # Confirmed controls contains only approved mappings
    assert "CTRL-FIN-APPROVAL-THRESHOLDS" in bl["confirmed_control_ids"]
    # Rejected mapping is excluded
    assert "CTRL-TECH-OBSERVABILITY" not in bl["confirmed_control_ids"]
    # Proposed (unreviewed) mapping is excluded from confirmed controls and recorded in pending
    assert "CTRL-FAIR-BIAS-DETECTION" not in bl["confirmed_control_ids"]
    c2_id = clauses[2]["clause_id"]
    assert c2_id in bl["pending_clause_ids"]


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Baseline version creation and immutability
# ─────────────────────────────────────────────────────────────────────────────
def test_8_baseline_versioning_and_immutability():
    tenant = f"tenant-immut-{uuid.uuid4()}"
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Cybersecurity Policy",
        text="All customer data must be encrypted with AES-256.",
    )
    store.save_enterprise_policy(tenant, pol)

    # Create baseline v1 (revision 1)
    bl_v1 = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Security Baseline",
        policies=[pol],
        version="1.0.0",
        revision=1,
    )
    store.save_enterprise_baseline(tenant, bl_v1)
    assert bl_v1.baseline_sha256 is not None
    sha_v1 = bl_v1.baseline_sha256

    # Attempting to mutate an active baseline in-place with different fingerprint raises ConflictError
    tampered_bl = bl_v1.model_copy(
        update={"baseline_sha256": "tampered-hash-12345"}
    )
    with pytest.raises(ConflictError):
        store.save_enterprise_baseline(tenant, tampered_bl)

    # Creating a new revision increments version
    pol2 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Cybersecurity Policy",
        text="All customer data must be encrypted with AES-256 and HSM keys.",
        version="2.0.0",
    )
    store.save_enterprise_policy(tenant, pol2)

    bl_v2 = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Security Baseline",
        policies=[pol2],
        version="2.0.0",
        revision=2,
    )
    store.save_enterprise_baseline(tenant, bl_v2)
    assert bl_v2.revision == 2
    assert bl_v2.baseline_sha256 != sha_v1


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Cross-tenant access attempts
# ─────────────────────────────────────────────────────────────────────────────
def test_9_cross_tenant_access_isolation(client):
    tenant_a = f"tenant-a-{uuid.uuid4()}"
    tenant_b = f"tenant-b-{uuid.uuid4()}"

    # Tenant A creates policy and baseline
    res_pol_a = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "name": "Secret Bank A Policy",
            "text": "Proprietary credit scoring threshold AUD 750.",
        },
    )
    assert res_pol_a.status_code == 201
    pol_a_id = res_pol_a.json()["policy_id"]

    res_bl_a = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "name": "Bank A Baseline",
            "policy_ids": [pol_a_id],
        },
    )
    assert res_bl_a.status_code == 201
    bl_a_id = res_bl_a.json()["baseline_id"]

    # Tenant B attempts to access Tenant A's baseline directly -> 404
    res_b_get_bl = client.get(
        f"/v1/enterprise/baselines/{bl_a_id}",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert res_b_get_bl.status_code == 404

    # Tenant B attempts to access Tenant A's policy directly -> 404
    res_b_get_pol = client.get(
        f"/v1/enterprise/policies/{pol_a_id}",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert res_b_get_pol.status_code == 404

    # Tenant B attempts to create a baseline using Tenant A's policy ID -> 404
    res_b_create_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "name": "Intruder Baseline",
            "policy_ids": [pol_a_id],
        },
    )
    assert res_b_create_bl.status_code == 404

    # Tenant B lists baselines -> empty list, Tenant A baseline is invisible
    res_b_list = client.get(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert res_b_list.status_code == 200
    assert len(res_b_list.json()) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Source and audit traceability
# ─────────────────────────────────────────────────────────────────────────────
def test_10_source_and_audit_traceability(client):
    tenant = f"tenant-trace-{uuid.uuid4()}"

    # 1. Ingest policy
    res_pol = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Audit Traceability Standard",
            "text": "All transactions above AUD 500 require authorised officer approval.",
            "version": "1.0.0",
        },
    )
    assert res_pol.status_code == 201
    pol_id = res_pol.json()["policy_id"]
    clause_id = res_pol.json()["clauses"][0]["clause_id"]

    # 2. Review clause
    res_rev = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "confirmed",
            "actor": "senior-grc-auditor",
            "role": "compliance",
            "review_comment": "Confirmed alignment with APRA CPS 230 Delegated Authorities",
        },
    )
    assert res_rev.status_code == 200
    clause_data = res_rev.json()
    assert clause_data["reviewer_actor"] == "senior-grc-auditor"
    assert clause_data["reviewer_role"] == "compliance"
    assert clause_data["reviewed_at"] is not None

    # 3. Create baseline
    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Traceable Baseline",
            "policy_ids": [pol_id],
        },
    )
    assert res_bl.status_code == 201
    bl_id = res_bl.json()["baseline_id"]

    # 4. Verify audit trail in store
    audit_events = store.audit_events(tenant)
    actions = [e["action"] for e in audit_events]
    assert "enterprise_policy.saved" in actions
    assert "clause.reviewed" in actions
    assert "enterprise_baseline.saved" in actions

    # Verify review detail is recorded
    review_event = next(e for e in audit_events if e["action"] == "clause.reviewed")
    assert review_event["actor"] == "senior-grc-auditor"
    assert review_event["detail"]["status"] == "confirmed"
