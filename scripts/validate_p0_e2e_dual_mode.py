"""End-to-End Production API Validation Script for Prompt 2E.

Executes actual HTTP requests via TestClient for:
1. Scenario A: Regulatory-Only Assessment
2. Scenario B: Enterprise-Enhanced Assessment (Multi-Policy Baseline + Gated Approval)
3. Mode Comparison & Verification
4. Tenant Isolation & Cryptographic Baseline Tampering Checks
"""

import json
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_aiaf_question_bank
from banking_crosswalk.store import store


def run_e2e_validation():
    client = TestClient(app)
    output_dir = Path(__file__).resolve().parent.parent / "e2e_artifacts"
    output_dir.mkdir(exist_ok=True)

    print("=" * 80)
    print("DEEPAUDIT CROSSWALK: PROMPT 2E END-TO-END DUAL-MODE API VALIDATION")
    print("=" * 80)

    # ─────────────────────────────────────────────────────────────────────────
    # SCENARIO A: Regulatory-Only Assessment (Default Mode)
    # ─────────────────────────────────────────────────────────────────────────
    tenant_a = f"tenant-reg-only-{uuid.uuid4()}"
    print(f"\n[Scenario A] Executing Regulatory-Only Assessment for Tenant: {tenant_a}")

    # 1. Tenant A has ZERO enterprise policies or baselines.
    # 2. Supply synthetic questionnaire via built-in catalog or import
    qbank = store.save_questionnaire(tenant_a, load_aiaf_question_bank())
    q_id = qbank.metadata.questionnaire_id

    req_payload_a = {
        "assessment_mode": "regulatory_only",
        "questionnaire_id": q_id,
        "use_case": {
            "name": "Dispute and Refund AI Agent",
            "apra_regulated": True,
            "handles_personal_information": True,
            "idr_obligations": True,
            "assists_consumer_credit_decision": False,
            "approval_threshold_aud": 1000.0,
            "approval_threshold_operator": ">",
        },
        "persist": False,
    }

    res_a = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_a},
        json=req_payload_a,
    )
    assert res_a.status_code == 201, f"Scenario A failed: {res_a.text}"
    data_a = res_a.json()

    # Save artifacts
    with open(output_dir / "scenario_a_request.json", "w", encoding="utf-8") as f:
        json.dump(req_payload_a, f, indent=2)
    with open(output_dir / "scenario_a_response.json", "w", encoding="utf-8") as f:
        json.dump(data_a, f, indent=2)

    print(f"  -> HTTP {res_a.status_code} Created")
    print(f"  -> Assessment ID: {data_a['assessment_id']}")
    print(f"  -> Assessment Mode: {data_a['assessment_mode']}")
    print(f"  -> Enterprise Baseline ID: {data_a['enterprise_baseline_id']} (Expected: None)")
    print(f"  -> Applicable Obligations Evaluated: {len(data_a['applicable_obligation_ids'])}")
    print(f"  -> Regulatory Gaps Identified: {len(data_a['gaps'])}")
    print(f"  -> Enterprise Gaps: {len(data_a['enterprise_gaps'])} (Expected: 0)")
    assert data_a["assessment_mode"] == "regulatory_only"
    assert data_a["enterprise_baseline_id"] is None
    assert len(data_a["enterprise_gaps"]) == 0
    assert not any(g["source_type"] == "enterprise_policy" for g in data_a["gaps"])
    print("  [PASS] Scenario A Regulatory-Only Assessment verified with zero enterprise data leakage.")

    # ─────────────────────────────────────────────────────────────────────────
    # SCENARIO B: Enterprise-Enhanced Assessment (Optional Mode)
    # ─────────────────────────────────────────────────────────────────────────
    tenant_b = f"tenant-ent-enhanced-{uuid.uuid4()}"
    print(f"\n[Scenario B] Executing Enterprise-Enhanced Assessment for Tenant: {tenant_b}")

    # 1. Tenant B imports multiple enterprise policies covering AI Governance, Cyber, Privacy, Thresholds
    policies_data = [
        {
            "name": "Enterprise AI Governance & Oversight Policy",
            "category": "governance",
            "version": "1.2.0",
            "text": (
                "Section 1. Operational Oversight:\n"
                "All automated customer refund credits exceeding AUD 500 must receive manual approval by an authorised officer prior to execution.\n"
                "Section 2. Non-Circumvention:\n"
                "Under no circumstances shall human approval be bypassed or omitted for automated decisions.\n"
                "Section 3. Model Inventory:\n"
                "All production AI models must be registered in the enterprise model catalog with designated risk owners."
            ),
        },
        {
            "name": "Enterprise Information Security & Privacy Policy",
            "category": "security",
            "version": "2.0.0",
            "text": (
                "Clause 1. Access Control:\n"
                "Cryptographic keys and production customer credentials must reside in dedicated hardware security modules.\n"
                "Clause 2. Data Sovereignty:\n"
                "Customer personal information must be stored within Australian data centers with zero unapproved extraterritorial transfer."
            ),
        },
    ]

    imported_policy_ids = []
    clauses_to_approve = []
    clauses_to_leave_proposed = []

    for p in policies_data:
        p_res = client.post(
            "/v1/enterprise/policies/import",
            headers={"X-Tenant-ID": tenant_b},
            json=p,
        )
        assert p_res.status_code == 201
        p_obj = p_res.json()
        imported_policy_ids.append(p_obj["policy_id"])
        print(f"  -> Imported Policy: '{p_obj['name']}' (v{p_obj['version']}) with {len(p_obj['clauses'])} clauses")

        # Selectively approve clauses: approve clauses with AUD 500 threshold and access control
        for c in p_obj["clauses"]:
            if "500" in c["text"] or "hardware security modules" in c["text"]:
                clauses_to_approve.append(c["clause_id"])
            else:
                clauses_to_leave_proposed.append(c["clause_id"])

    # 2. Review and approve selected clauses
    for cid in clauses_to_approve:
        rev_res = client.put(
            f"/v1/enterprise/clauses/{cid}/review",
            headers={"X-Tenant-ID": tenant_b},
            json={
                "status": "approved",
                "actor": "chief-risk-officer@bank.example",
                "role": "Chief Risk Officer",
                "review_comment": "Approved for baseline compliance integration",
            },
        )
        assert rev_res.status_code == 200

    print(f"  -> Approved {len(clauses_to_approve)} clauses; left {len(clauses_to_leave_proposed)} as proposed.")

    # 3. Compile versioned Enterprise Baseline
    bl_res = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "name": "Australian Banking Governance & Controls Baseline",
            "policy_ids": imported_policy_ids,
            "version": "2026.Q1",
            "description": "Baseline incorporating approved credit risk, privacy and threshold policies.",
            "status": "active",
        },
    )
    assert bl_res.status_code == 201
    baseline_data = bl_res.json()
    baseline_id = baseline_data["baseline_id"]
    baseline_sha = baseline_data["baseline_sha256"]
    print(f"  -> Compiled Baseline ID: {baseline_id} (v{baseline_data['version']}, rev {baseline_data['revision']})")
    print(f"  -> Cryptographic SHA-256 Fingerprint: {baseline_sha[:24]}...")
    print(f"  -> Confirmed Controls: {baseline_data['confirmed_control_ids']}")
    print(f"  -> Pending Clauses: {len(baseline_data['pending_clause_ids'])}")

    # 4. Save identical questionnaire for Tenant B
    qbank_b = store.save_questionnaire(tenant_b, load_aiaf_question_bank())
    q_id_b = qbank_b.metadata.questionnaire_id

    # 5. Execute Enterprise-Enhanced Assessment with structured Use Case containing threshold mismatch:
    # Policy requires approval > AUD 500, but use case configures threshold > AUD 1,000!
    req_payload_b = {
        "assessment_mode": "enterprise_enhanced",
        "enterprise_baseline_id": baseline_id,
        "enterprise_baseline_version": "2026.Q1",
        "questionnaire_id": q_id_b,
        "use_case": {
            "name": "Dispute and Refund AI Agent",
            "apra_regulated": True,
            "handles_personal_information": True,
            "idr_obligations": True,
            "assists_consumer_credit_decision": False,
            "approval_threshold_aud": 1000.0,
            "approval_threshold_operator": ">",
        },
        "persist": False,
    }

    res_b = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_b},
        json=req_payload_b,
    )
    assert res_b.status_code == 201, f"Scenario B failed: {res_b.text}"
    data_b = res_b.json()

    # Save artifacts
    with open(output_dir / "scenario_b_request.json", "w", encoding="utf-8") as f:
        json.dump(req_payload_b, f, indent=2)
    with open(output_dir / "scenario_b_response.json", "w", encoding="utf-8") as f:
        json.dump(data_b, f, indent=2)

    print(f"  -> HTTP {res_b.status_code} Created")
    print(f"  -> Assessment ID: {data_b['assessment_id']}")
    print(f"  -> Assessment Mode: {data_b['assessment_mode']}")
    print(f"  -> Baseline ID Resolved: {data_b['enterprise_baseline_id']}")
    print(f"  -> Applicable Regulatory Obligations: {len(data_b['applicable_obligation_ids'])}")
    print(f"  -> Applicable Enterprise Requirements: {len(data_b['applicable_enterprise_requirement_ids'])}")
    print(f"  -> Regulatory Gaps: {len([g for g in data_b['gaps'] if g['source_type'] == 'regulatory'])}")
    print(f"  -> Enterprise Gaps: {len(data_b['enterprise_gaps'])}")

    # Verify threshold conflict gap
    threshold_conflicts = [
        g for g in data_b["enterprise_gaps"]
        if g["gap_type"] == "control_conflict"
    ]
    print(f"  -> Threshold Conflicts Detected: {len(threshold_conflicts)}")
    if threshold_conflicts:
        tc = threshold_conflicts[0]
        print(f"     Title: {tc['title']}")
        print(f"     Required Threshold: AUD {tc['required_threshold']}")
        print(f"     Use Case Threshold: AUD {tc['use_case_threshold']}")
        print(f"     Severity: {tc['severity']}")
        print(f"     Recommendation: {tc['recommendation']}")

    assert len(threshold_conflicts) == 1
    assert threshold_conflicts[0]["required_threshold"] == 500.0
    assert threshold_conflicts[0]["use_case_threshold"] == 1000.0
    print("  [PASS] Scenario B Enterprise-Enhanced Assessment verified with threshold validation.")

    # ─────────────────────────────────────────────────────────────────────────
    # SCENARIO COMPARISON & DUAL-MODE ISOLATION CHECK
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Scenario Comparison] Comparing Mode A and Mode B on identical questionnaire:")
    print(f"  -> Mode A Applicable Obligations: {len(data_a['applicable_obligation_ids'])}")
    print(f"  -> Mode B Applicable Obligations: {len(data_b['applicable_obligation_ids'])}")
    assert data_a["applicable_obligation_ids"] == data_b["applicable_obligation_ids"]
    print("  -> Applicable shared regulatory obligations are 100% IDENTICAL between Mode A and Mode B.")

    # Execute Mode A for Tenant B (who HAS an active baseline) to ensure Mode A remains independent
    res_b_as_mode_a = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "assessment_mode": "regulatory_only",
            "questionnaire_id": q_id_b,
            "use_case": req_payload_b["use_case"],
            "persist": False,
        },
    )
    assert res_b_as_mode_a.status_code == 201
    data_b_mode_a = res_b_as_mode_a.json()
    assert data_b_mode_a["enterprise_baseline_id"] is None
    assert len(data_b_mode_a["enterprise_gaps"]) == 0
    assert not any(g["gap_type"] == "control_conflict" for g in data_b_mode_a["gaps"])
    print("  [PASS] Tenant B with active baseline can execute Mode A without enterprise threshold conflicts.")

    # ─────────────────────────────────────────────────────────────────────────
    # TENANT ISOLATION CHECK
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Security Verification] Testing Tenant Isolation:")
    # Tenant A attempts to assess using Tenant B's baseline ID
    res_cross_tenant = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline_id,
            "questionnaire_id": q_id,
            "use_case": req_payload_a["use_case"],
            "persist": False,
        },
    )
    assert res_cross_tenant.status_code == 404
    print(f"  -> Cross-tenant baseline access returned HTTP {res_cross_tenant.status_code} (Expected 404 Not Found).")
    print("  [PASS] Tenant isolation strictly prevents cross-tenant baseline consumption.")

    # ─────────────────────────────────────────────────────────────────────────
    # CRYPTOGRAPHIC FINGERPRINT INTEGRITY CHECK
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[Integrity Verification] Testing Baseline Fingerprint Tampering:")
    # Tamper directly with the underlying stored record to simulate external tampering
    stored_bl = store.get_enterprise_baseline(tenant_b, baseline_id)
    tampered_bl = stored_bl.model_copy(
        update={
            "clause_snapshots": [
                stored_bl.clause_snapshots[0].model_copy(
                    update={"text": "TAMPERED TEXT CONTENT TO ALTER BASELINE"}
                )
            ]
        }
    )
    store._enterprise_baselines[tenant_b][baseline_id] = tampered_bl

    res_tampered = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant_b},
        json=req_payload_b,
    )
    assert res_tampered.status_code == 422
    assert "cryptographic fingerprint mismatch" in res_tampered.json()["detail"].lower()
    print(f"  -> Tampered baseline returned HTTP {res_tampered.status_code} Unprocessable Entity.")
    print("  [PASS] Cryptographic baseline integrity check detects tampered content and fails closed.")

    # Restore original baseline
    store._enterprise_baselines[tenant_b][baseline_id] = stored_bl

    print("\n" + "=" * 80)
    print("ALL PROMPT 2E END-TO-END VALIDATION CHECKS PASSED SUCCESSFULLY.")
    print(f"Artifacts saved to: {output_dir}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_e2e_validation())
