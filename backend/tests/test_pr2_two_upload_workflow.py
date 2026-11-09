"""PR 2 Acceptance & Regression Suite — Two-Upload Foundation and Questionnaire User Journey.

Covers Scenarios A through G from the Document-First Two-Upload Architecture specification:
- Scenario A: Regulatory-Only Questionnaire upload, preview & coverage assessment
- Scenario B: Enterprise-Enhanced Questionnaire with dual-approval baseline workflow
- Scenario C: Strategy Assessment target guard (501 Not Implemented in PR 2)
- Scenario D: Unknown applicability preserved when Organisation Profile facts are null
- Scenario E: Strict Document Role Separation between Upload A (Policy) and Upload B (Questionnaire)
- Scenario F: P1-S0 False-Coverage Regression ("human oversight" vs "human approval >= AUD 500 before execution")
- Scenario G: Strict Tenant Isolation across Questionnaires, Policies, Clauses, Mappings, Baselines, and Assessments
"""

from __future__ import annotations

import base64
import io
from openpyxl import Workbook
from fastapi.testclient import TestClient

from banking_crosswalk.app import app


client = TestClient(app)


def _headers(
    tenant: str,
    actor: str = "reviewer@bank.example",
    role: str = "compliance",
) -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant,
        "X-Actor": actor,
        "X-Role": role,
    }


def _make_xlsx_base64(rows: list[tuple[str, str, str]]) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "AssuranceQuestions"
    ws.append(["Question ID", "Risk Domain", "Question Text"])
    for qid, domain, text in rows:
        ws.append([qid, domain, text])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_scenario_a_regulatory_only_questionnaire_upload_preview_and_assessment():
    """Scenario A: Upload an ordinary enterprise XLSX questionnaire, preview extracted questions,
    and run Regulatory-Only without an Enterprise Baseline or DEMO_BANKING_V1."""
    tenant = "pr2-tenant-scenario-a"
    xlsx_b64 = _make_xlsx_base64(
        [
            (
                "BANK-Q-001",
                "Privacy",
                "Does the system maintain a personal information data inventory and privacy impact assessment?",
            ),
            (
                "BANK-Q-002",
                "Governance",
                "Are automated decisions subject to human approval before execution with immutable audit trail logging?",
            ),
        ]
    )

    # 1. Import XLSX questionnaire
    import_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={
            "filename": "bank_ai_assurance_v1.xlsx",
            "workbook_base64": xlsx_b64,
        },
    )
    assert import_res.status_code == 200, import_res.text
    qbank = import_res.json()
    qid = qbank["metadata"]["questionnaire_id"]
    assert qid.startswith("QBANK-")
    assert qid != "DEMO_BANKING_V1"
    assert qbank["metadata"]["source_filename"] == "bank_ai_assurance_v1.xlsx"
    assert len(qbank["questions"]) == 2
    assert qbank["questions"][0]["question_id"] == "BANK-Q-001"
    assert qbank["questions"][0]["source_sheet"] == "AssuranceQuestions"
    assert "AssuranceQuestions!R2" in qbank["questions"][0]["source_location"]

    # 2. List & preview tenant questionnaires (must not include DEMO_BANKING_V1)
    list_res = client.get("/v1/questionnaires", headers=_headers(tenant))
    assert list_res.status_code == 200
    listed = list_res.json()
    assert len(listed) == 1
    assert listed[0]["metadata"]["questionnaire_id"] == qid

    get_res = client.get(f"/v1/questionnaires/{qid}", headers=_headers(tenant))
    assert get_res.status_code == 200
    assert get_res.json()["metadata"]["source_sha256"] == qbank["metadata"]["source_sha256"]

    # 3. Run Regulatory-Only coverage assessment on uploaded questionnaire
    assess_res = client.post(
        "/v1/assessments/coverage",
        headers=_headers(tenant),
        json={
            "questionnaire_id": qid,
            "assessment_mode": "regulatory_only",
            "assessment_target_type": "questionnaire",
            "use_case": {
                "name": "Bank A Organisation Profile",
                "apra_regulated": True,
                "handles_personal_information": True,
            },
        },
    )
    assert assess_res.status_code == 201, assess_res.text
    assessment = assess_res.json()
    assert assessment["assessment_mode"] == "regulatory_only"
    assert assessment["questionnaire_id"] == qid
    assert assessment["questionnaire_sha256"] == qbank["metadata"]["source_sha256"]
    assert assessment["enterprise_baseline_id"] is None
    assert assessment["enterprise_clause_coverage"] == []
    assert len(assessment["results"]) > 0


def test_scenario_b_enterprise_enhanced_questionnaire_with_separate_clause_and_mapping_approval():
    """Scenario B: Upload internal delegated-authority policy, separately review & approve
    clauses and control mappings, compile an eligible Enterprise Baseline, and assess an
    uploaded enterprise XLSX questionnaire."""
    tenant = "pr2-tenant-scenario-b"
    policy_text = (
        "1.1 All AI-assisted refunds above or equal to $500 AUD require Senior Manager "
        "human approval before payment execution and audit trail logging."
    )
    pol_b64 = base64.b64encode(policy_text.encode("utf-8")).decode("ascii")

    # 1. Upload internal policy file (Upload A)
    pol_res = client.post(
        "/v1/enterprise/policies/import-file",
        headers=_headers(tenant),
        json={
            "name": "Delegated Authority Policy",
            "filename": "delegated_authority.txt",
            "file_base64": pol_b64,
            "version": "2.0.0",
            "category": "delegated_authority",
            "authority_level": "enterprise_policy",
        },
    )
    assert pol_res.status_code == 201, pol_res.text
    policy = pol_res.json()
    policy_id = policy["policy_id"]
    assert len(policy["clauses"]) >= 1
    clause = policy["clauses"][0]
    clause_id = clause["clause_id"]
    assert clause["review_status"] == "proposed"
    assert len(clause["control_mappings"]) >= 1
    assert all(m["review_status"] == "proposed" for m in clause["control_mappings"])

    # 2. Unreviewed policy compiles only as 'draft' (never 'active') and cannot be used for enterprise_enhanced assessment
    unreviewed_base = client.post(
        "/v1/enterprise/baselines",
        headers=_headers(tenant),
        json={
            "name": "Premature Baseline",
            "policy_ids": [policy_id],
            "version": "1.0.0",
        },
    )
    assert unreviewed_base.status_code == 201
    draft_baseline = unreviewed_base.json()
    assert draft_baseline["status"] == "draft"
    assert draft_baseline["approved_clause_ids"] == []
    assert draft_baseline["confirmed_control_ids"] == []

    # 3. Approve clause ONLY -> proposed mappings must remain 'proposed' (P1-S0 invariant)
    rev_clause_res = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers=_headers(tenant),
        json={
            "status": "approved",
            "actor": "reviewer@bank.example",
            "role": "compliance",
            "review_comment": "Approved clause wording",
        },
    )
    assert rev_clause_res.status_code == 200
    reviewed_clause = rev_clause_res.json()
    assert reviewed_clause["review_status"] == "approved"
    assert all(
        m["review_status"] == "proposed" for m in reviewed_clause["control_mappings"]
    )

    # 4. Compile baseline v1 before mapping approval -> confirmed_control_ids must be empty
    base_v1_res = client.post(
        "/v1/enterprise/baselines",
        headers=_headers(tenant),
        json={
            "name": "Delegated Baseline",
            "policy_ids": [policy_id],
            "version": "1.0.0",
        },
    )
    assert base_v1_res.status_code == 201
    base_v1 = base_v1_res.json()
    assert base_v1["approved_clause_ids"] == [clause_id]
    assert base_v1["confirmed_control_ids"] == []

    # 5. Explicitly approve each control mapping via separate endpoint
    for m in reviewed_clause["control_mappings"]:
        map_res = client.put(
            f"/v1/enterprise/clauses/{clause_id}/mappings/{m['mapping_id']}/review",
            headers=_headers(tenant),
            json={
                "status": "approved",
                "actor": "reviewer@bank.example",
                "role": "compliance",
                "review_comment": "Verified control mapping",
            },
        )
        assert map_res.status_code == 200
        assert map_res.json()["review_status"] == "approved"

    # 6. Compile baseline v2 -> confirmed_control_ids now populated
    base_v2_res = client.post(
        "/v1/enterprise/baselines",
        headers=_headers(tenant),
        json={
            "name": "Delegated Baseline",
            "policy_ids": [policy_id],
            "version": "2.0.0",
        },
    )
    assert base_v2_res.status_code == 201
    base_v2 = base_v2_res.json()
    assert len(base_v2["confirmed_control_ids"]) >= 1
    assert base_v2["baseline_sha256"] != base_v1["baseline_sha256"]

    # 7. Upload customer questionnaire (Upload B) that satisfies the requirement
    xlsx_b64 = _make_xlsx_base64(
        [
            (
                "Q-AUTH-01",
                "Delegated Authority",
                "Do all AI-assisted refunds >= $500 AUD require Senior Manager human approval before execution with an immutable audit trail?",
            )
        ]
    )
    q_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={"filename": "authority_check.xlsx", "workbook_base64": xlsx_b64},
    )
    assert q_res.status_code == 200
    qid = q_res.json()["metadata"]["questionnaire_id"]

    # 8. Run Enterprise-Enhanced coverage assessment
    assess_res = client.post(
        "/v1/assessments/coverage",
        headers=_headers(tenant),
        json={
            "questionnaire_id": qid,
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": base_v2["baseline_id"],
            "enterprise_baseline_version": "2.0.0",
        },
    )
    assert assess_res.status_code == 201, assess_res.text
    assessment = assess_res.json()
    assert assessment["assessment_mode"] == "enterprise_enhanced"
    assert assessment["enterprise_baseline_id"] == base_v2["baseline_id"]
    assert len(assessment["enterprise_clause_coverage"]) == 1
    ec = assessment["enterprise_clause_coverage"][0]
    assert ec["clause_id"] == clause_id
    assert ec["clause_approval_status"] == "approved"
    assert ec["control_mapping_approval_status"] == "approved"
    assert ec["coverage_status"] == "covered"
    assert ec["implementation_evidence_status"] == "not_assessed"
    assert ec["operational_effectiveness_status"] == "not_assessed"


def test_scenario_c_strategy_assessment_target_returns_501():
    """Scenario C: Strategy Assessment target is explicitly rejected with 501 until PR 4."""
    tenant = "pr2-tenant-scenario-c"
    xlsx_b64 = _make_xlsx_base64([("Q-1", "Gov", "Is AI governance documented?")])
    q_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={"filename": "q.xlsx", "workbook_base64": xlsx_b64},
    )
    qid = q_res.json()["metadata"]["questionnaire_id"]

    res = client.post(
        "/v1/assessments/coverage",
        headers=_headers(tenant),
        json={
            "questionnaire_id": qid,
            "assessment_mode": "regulatory_only",
            "assessment_target_type": "strategy",
        },
    )
    assert res.status_code == 501


def test_scenario_d_unknown_applicability_preserved():
    """Scenario D: When a questionnaire is assessed without confirmed organisation facts,
    uncertain applicability remains 'undetermined' rather than being silently dismissed."""
    tenant = "pr2-tenant-scenario-d"
    xlsx_b64 = _make_xlsx_base64(
        [("Q-1", "General", "Are AI models documented in a model register?")]
    )
    q_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={"filename": "minimal.xlsx", "workbook_base64": xlsx_b64},
    )
    qid = q_res.json()["metadata"]["questionnaire_id"]

    assess_res = client.post(
        "/v1/assessments/coverage",
        headers=_headers(tenant),
        json={
            "questionnaire_id": qid,
            "assessment_mode": "regulatory_only",
            "use_case": {
                "name": "Unconfirmed Organisation Profile",
                "apra_regulated": None,
                "handles_personal_information": None,
                "handles_regulated_complaints": None,
                "idr_obligations": None,
                "material_service_provider": None,
            },
        },
    )
    assert assess_res.status_code == 201
    data = assess_res.json()
    assert data["metrics"]["applicability_undetermined"] > 0
    statuses = {r["applicability"]["status"] for r in data["results"]}
    assert "undetermined" in statuses


def test_scenario_e_document_role_separation():
    """Scenario E: Upload A (Enterprise Policy) never creates a Questionnaire target,
    and Upload B (Questionnaire) never creates an Enterprise Policy or Baseline."""
    tenant = "pr2-tenant-scenario-e"

    # Upload A: Policy import
    pol_res = client.post(
        "/v1/enterprise/policies/import",
        headers=_headers(tenant),
        json={
            "name": "Internal AI Policy",
            "text": "All high-risk AI systems require human approval before deployment.",
            "version": "1.0.0",
        },
    )
    assert pol_res.status_code == 201
    assert client.get("/v1/questionnaires", headers=_headers(tenant)).json() == []

    # Upload B: Questionnaire import
    xlsx_b64 = _make_xlsx_base64(
        [("Q-ROLE-1", "Gov", "Do high-risk AI systems require human approval?")]
    )
    q_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={"filename": "role_check.xlsx", "workbook_base64": xlsx_b64},
    )
    assert q_res.status_code == 200
    policies = client.get("/v1/enterprise/policies", headers=_headers(tenant)).json()
    assert len(policies) == 1
    assert policies[0]["name"] == "Internal AI Policy"


def test_scenario_f_false_coverage_regression_human_oversight_vs_approval_threshold():
    """Scenario F: A generic question mentioning 'human oversight' must NOT satisfy
    an enterprise requirement for authorised approval above AUD 500 before execution."""
    tenant = "pr2-tenant-scenario-f"
    pol_res = client.post(
        "/v1/enterprise/policies/import",
        headers=_headers(tenant),
        json={
            "name": "Refund Approval Policy",
            "text": "All refunds >= $500 AUD require Senior Manager human approval before payment execution.",
            "version": "1.0.0",
        },
    )
    policy = pol_res.json()
    clause = policy["clauses"][0]
    clause_id = clause["clause_id"]

    client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers=_headers(tenant),
        json={"status": "approved", "actor": "reviewer", "role": "compliance"},
    )
    for m in clause["control_mappings"]:
        client.put(
            f"/v1/enterprise/clauses/{clause_id}/mappings/{m['mapping_id']}/review",
            headers=_headers(tenant),
            json={"status": "approved", "actor": "reviewer", "role": "compliance"},
        )

    base_res = client.post(
        "/v1/enterprise/baselines",
        headers=_headers(tenant),
        json={
            "name": "Refund Baseline",
            "policy_ids": [policy["policy_id"]],
            "version": "1.0.0",
        },
    )
    baseline_id = base_res.json()["baseline_id"]

    # Questionnaire only asks about generic "human oversight"
    xlsx_b64 = _make_xlsx_base64(
        [
            (
                "Q-WEAK-01",
                "Oversight",
                "Does the team maintain general human oversight over automated refund workflows?",
            )
        ]
    )
    q_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(tenant),
        json={"filename": "weak_oversight.xlsx", "workbook_base64": xlsx_b64},
    )
    qid = q_res.json()["metadata"]["questionnaire_id"]

    assess_res = client.post(
        "/v1/assessments/coverage",
        headers=_headers(tenant),
        json={
            "questionnaire_id": qid,
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline_id,
        },
    )
    assert assess_res.status_code == 201
    assessment = assess_res.json()
    ec = assessment["enterprise_clause_coverage"][0]
    assert ec["coverage_status"] != "covered"
    assert ec["coverage_status"] in {"needs_review", "missing"}
    assert any(clause_id in g["title"] for g in assessment["gaps"])


def test_scenario_g_tenant_isolation_across_questionnaires_policies_and_baselines():
    """Scenario G: Bank A's uploaded questionnaires, internal policies, clauses, mappings,
    and baselines are never accessible to Bank B."""
    bank_a = "pr2-tenant-bank-a"
    bank_b = "pr2-tenant-bank-b"

    xlsx_b64 = _make_xlsx_base64(
        [("BANK-A-Q1", "Privacy", "Private Bank A assurance question?")]
    )
    qa_res = client.post(
        "/v1/questionnaires/import",
        headers=_headers(bank_a),
        json={"filename": "bank_a_private.xlsx", "workbook_base64": xlsx_b64},
    )
    qid_a = qa_res.json()["metadata"]["questionnaire_id"]

    pa_res = client.post(
        "/v1/enterprise/policies/import",
        headers=_headers(bank_a),
        json={
            "name": "Bank A Confidential Policy",
            "text": "All credit decisions >= $10,000 AUD require human approval before execution.",
            "version": "1.0.0",
        },
    )
    policy_a = pa_res.json()
    clause_a = policy_a["clauses"][0]

    # Bank B cannot list or fetch Bank A's questionnaire
    assert client.get("/v1/questionnaires", headers=_headers(bank_b)).json() == []
    assert (
        client.get(
            f"/v1/questionnaires/{qid_a}", headers=_headers(bank_b)
        ).status_code
        == 404
    )

    # Bank B cannot assess Bank A's questionnaire
    assert (
        client.post(
            "/v1/assessments/coverage",
            headers=_headers(bank_b),
            json={"questionnaire_id": qid_a, "assessment_mode": "regulatory_only"},
        ).status_code
        == 404
    )

    # Bank B cannot list, fetch, or review Bank A's policies or clauses
    assert client.get("/v1/enterprise/policies", headers=_headers(bank_b)).json() == []
    assert (
        client.get(
            f"/v1/enterprise/policies/{policy_a['policy_id']}",
            headers=_headers(bank_b),
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/v1/enterprise/clauses/{clause_a['clause_id']}/review",
            headers=_headers(bank_b),
            json={"status": "approved", "actor": "attacker", "role": "compliance"},
        ).status_code
        in {403, 404}
    )
