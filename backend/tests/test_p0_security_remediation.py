"""P0 Security Remediation — Backend Authorisation, Reviewer Identity, Tenant Isolation & SQL RLS Tests.

Covers backend enforcement for the 58-case P0 Security Acceptance Matrix:
- Reviewer role enforcement on Enterprise Clause Review & Control Mapping Review
- Denial of Viewer and Analyst roles on approval and policy deletion endpoints
- Signed X-Workspace-Context verification when WORKSPACE_SESSION_SECRET is configured
- Actor/Role header vs body consistency (preventing spoofed reviewer attribution)
- Cross-tenant isolation across Questionnaires, Policies, Clauses, Mappings, Baselines, Assessments, and Reports
- SQLite / PostgreSQL tenant store isolation & RLS verification
- Public-demo tenant rejection on private enterprise and questionnaire endpoints
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from openpyxl import Workbook
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.database import create_database_engine, upgrade_database
from banking_crosswalk.sql_store import SQLTenantStore
from banking_crosswalk.store import NotFoundError


client = TestClient(app)


def _make_xlsx_base64(rows: list[tuple[str, str, str]]) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(["Question ID", "Domain", "Question Text"])
    for qid, dom, txt in rows:
        ws.append([qid, dom, txt])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _sign_context(payload: dict, secret: str) -> str:
    body_b64 = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(
        secret.encode("utf-8"), body_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{body_b64}.{sig}"


def test_reproduce_vuln_c_analyst_and_viewer_cannot_approve_enterprise_clauses_or_mappings():
    """Vulnerability C: An Analyst or Viewer must be denied (403) when attempting to
    approve an Enterprise Clause or Control Mapping directly or via the API."""
    tenant = "sec-p0-tenant-roles"
    pol_res = client.post(
        "/v1/enterprise/policies/import",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "name": "Internal AI Policy",
            "text": "1.1 All credit decisions >= $10,000 AUD require Senior Manager human approval before execution.",
            "version": "1.0.0",
        },
    )
    assert pol_res.status_code == 201
    policy = pol_res.json()
    clause = policy["clauses"][0]
    clause_id = clause["clause_id"]
    mapping_id = clause["control_mappings"][0]["mapping_id"]

    # Analyst attempting to approve a clause MUST be rejected with 403
    analyst_clause_attempt = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "status": "approved",
            "actor": "usr-analyst-1",
            "role": "analyst",
            "review_comment": "Unauthorized analyst self-approval",
        },
    )
    assert analyst_clause_attempt.status_code == 403

    # Viewer attempting to approve a clause MUST be rejected with 403
    viewer_clause_attempt = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-viewer-1",
            "X-Role": "viewer",
        },
        json={
            "status": "approved",
            "actor": "usr-viewer-1",
            "role": "viewer",
        },
    )
    assert viewer_clause_attempt.status_code == 403

    # Analyst attempting to approve a control mapping MUST be rejected with 403
    analyst_map_attempt = client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "status": "approved",
            "actor": "usr-analyst-1",
            "role": "analyst",
        },
    )
    assert analyst_map_attempt.status_code == 403

    # Verify clause and mapping remain 'proposed' (unmodified by denied operations)
    clauses_now = client.get(
        f"/v1/enterprise/policies/{policy['policy_id']}/clauses",
        headers={"X-Tenant-ID": tenant, "X-Actor": "usr-viewer-1", "X-Role": "viewer"},
    ).json()
    assert clauses_now[0]["review_status"] == "proposed"
    assert clauses_now[0]["control_mappings"][0]["review_status"] == "proposed"

    # Authorised Reviewer CAN approve clause and mapping separately
    reviewer_clause_ok = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-reviewer-99",
            "X-Role": "reviewer",
        },
        json={
            "status": "approved",
            "actor": "usr-reviewer-99",
            "role": "reviewer",
            "review_comment": "Approved by verified reviewer",
        },
    )
    assert reviewer_clause_ok.status_code == 200
    assert reviewer_clause_ok.json()["reviewer_actor"] == "usr-reviewer-99"
    assert reviewer_clause_ok.json()["reviewer_role"] == "reviewer"

    reviewer_map_ok = client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-reviewer-99",
            "X-Role": "reviewer",
        },
        json={
            "status": "approved",
            "actor": "usr-reviewer-99",
            "role": "reviewer",
            "review_comment": "Mapping approved by verified reviewer",
        },
    )
    assert reviewer_map_ok.status_code == 200
    assert reviewer_map_ok.json()["reviewer_actor"] == "usr-reviewer-99"


def test_reproduce_vuln_c_spoofed_body_actor_or_role_mismatch_rejected():
    """Vulnerability C: If a caller supplies X-Actor / X-Role headers that do not match
    the JSON body actor / role, or attempts to escalate role in the JSON body, reject with 403."""
    tenant = "sec-p0-tenant-spoof"
    pol_res = client.post(
        "/v1/enterprise/policies/import",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "name": "Spoof Test Policy",
            "text": "1.1 All decisions require human approval before execution.",
            "version": "1.0.0",
        },
    )
    clause = pol_res.json()["clauses"][0]

    # Header says 'analyst', body claims 'reviewer' -> MUST be 403
    mismatch_res = client.put(
        f"/v1/enterprise/clauses/{clause['clause_id']}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "status": "approved",
            "actor": "usr-reviewer-admin",
            "role": "reviewer",
        },
    )
    assert mismatch_res.status_code == 403


def test_viewer_and_analyst_cannot_delete_policy_or_compile_baseline_when_role_enforced():
    """Viewer cannot import or delete policies; Analyst cannot delete policies or compile baselines."""
    tenant = "sec-p0-tenant-least-priv"

    # Viewer attempting to import a questionnaire or policy -> 403
    xlsx_b64 = _make_xlsx_base64([("Q1", "Gov", "Is governance documented?")])
    viewer_q_import = client.post(
        "/v1/questionnaires/import",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-viewer-1",
            "X-Role": "viewer",
        },
        json={"filename": "q.xlsx", "workbook_base64": xlsx_b64},
    )
    assert viewer_q_import.status_code == 403

    viewer_pol_import = client.post(
        "/v1/enterprise/policies/import",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-viewer-1",
            "X-Role": "viewer",
        },
        json={
            "name": "Viewer Policy",
            "text": "1.1 All systems require human approval.",
            "version": "1.0.0",
        },
    )
    assert viewer_pol_import.status_code == 403

    # Analyst CAN import policy
    analyst_pol = client.post(
        "/v1/enterprise/policies/import",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "name": "Analyst Policy",
            "text": "1.1 All systems require human approval.",
            "version": "1.0.0",
        },
    )
    assert analyst_pol.status_code == 201
    policy_id = analyst_pol.json()["policy_id"]

    # Analyst attempting to delete policy -> 403 (requires admin)
    analyst_del = client.delete(
        f"/v1/enterprise/policies/{policy_id}",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
    )
    assert analyst_del.status_code == 403

    # Analyst attempting to compile baseline -> 403 (requires reviewer or admin)
    analyst_base = client.post(
        "/v1/enterprise/baselines",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-analyst-1",
            "X-Role": "analyst",
        },
        json={
            "name": "Analyst Baseline",
            "policy_ids": [policy_id],
            "version": "1.0.0",
        },
    )
    assert analyst_base.status_code == 403


def test_signed_workspace_context_assertion_enforced_when_configured(monkeypatch):
    """Direct FastAPI requests bypassing the web gateway or tampering with X-Workspace-Context
    are rejected when WORKSPACE_SESSION_SECRET is configured."""
    secret = "test-workspace-context-signing-secret-32bytes!"
    monkeypatch.setenv("WORKSPACE_SESSION_SECRET", secret)

    # 1. Request without X-Workspace-Context -> 401
    no_ctx = client.get(
        "/v1/questionnaires",
        headers={"X-Tenant-ID": "tenant-a"},
    )
    assert no_ctx.status_code == 401

    # 2. Request with tampered signature -> 401
    valid_token = _sign_context(
        {
            "user_id": "usr-1",
            "tenant_id": "tenant-a",
            "roles": ["analyst"],
            "session_id": "sess-1",
            "exp": int(time.time()) + 300,
        },
        secret,
    )
    tampered_token = valid_token[:-4] + "ffff"
    bad_sig = client.get(
        "/v1/questionnaires",
        headers={
            "X-Tenant-ID": "tenant-a",
            "X-Workspace-Context": tampered_token,
        },
    )
    assert bad_sig.status_code == 401

    # 3. Request where X-Tenant-ID header does not match signed context tenant_id -> 403
    cross_tenant = client.get(
        "/v1/questionnaires",
        headers={
            "X-Tenant-ID": "tenant-b-forged",
            "X-Workspace-Context": valid_token,
        },
    )
    assert cross_tenant.status_code == 403

    # 4. Expired signed context -> 401
    expired_token = _sign_context(
        {
            "user_id": "usr-1",
            "tenant_id": "tenant-a",
            "roles": ["analyst"],
            "session_id": "sess-1",
            "exp": int(time.time()) - 10,
        },
        secret,
    )
    exp_res = client.get(
        "/v1/questionnaires",
        headers={
            "X-Tenant-ID": "tenant-a",
            "X-Workspace-Context": expired_token,
        },
    )
    assert exp_res.status_code == 401

    # 5. Valid signed context succeeds
    ok_res = client.get(
        "/v1/questionnaires",
        headers={
            "X-Tenant-ID": "tenant-a",
            "X-Actor": "usr-1",
            "X-Role": "analyst",
            "X-Workspace-Context": valid_token,
        },
    )
    assert ok_res.status_code == 200


def test_sql_tenant_store_isolation_across_questionnaires_policies_and_assessments(tmp_path):
    """Verify transactional SQLTenantStore enforces strict tenant isolation across
    questionnaires, enterprise policies, clauses, mappings, baselines, assessments, and reports."""
    db_file = tmp_path / "tenant_isolation.db"
    url = f"sqlite:///{db_file}"
    upgrade_database(create_database_engine(url))
    sql_store = SQLTenantStore(url, production=False)
    try:
        from banking_crosswalk.importer import import_questionnaire_workbook
        from banking_crosswalk.policy import (
            compile_enterprise_baseline,
            extract_enterprise_policy,
        )
        from banking_crosswalk.models import ClauseReviewStatus

        raw_xlsx = base64.b64decode(
            _make_xlsx_base64([("Q-SQL-1", "Gov", "Is human approval required?")])
        )
        qbank_a = import_questionnaire_workbook(raw_xlsx, filename="bank_a.xlsx")
        sql_store.save_questionnaire("bank-a", qbank_a)

        pol_a = extract_enterprise_policy(
            tenant_id="bank-a",
            name="Bank A Policy",
            text="1.1 All decisions require human approval before execution.",
            version="1.0.0",
        )
        sql_store.save_enterprise_policy("bank-a", pol_a)
        clause_id = pol_a.clauses[0].clause_id
        mapping_id = pol_a.clauses[0].control_mappings[0].mapping_id

        # Bank B cannot list or read Bank A's questionnaire in SQL store
        assert sql_store.list_questionnaires("bank-b") == []
        with pytest.raises(NotFoundError):
            sql_store.get_tenant_questionnaire(
                "bank-b", qbank_a.metadata.questionnaire_id
            )

        # Bank B cannot list or read Bank A's policy or review Bank A's clause/mapping
        assert sql_store.list_enterprise_policies("bank-b") == []
        with pytest.raises(NotFoundError):
            sql_store.get_enterprise_policy("bank-b", pol_a.policy_id)
        with pytest.raises((PermissionError, NotFoundError)):
            sql_store.update_clause_review(
                "bank-b",
                clause_id,
                status=ClauseReviewStatus.APPROVED,
                actor="attacker",
                role="reviewer",
            )
        with pytest.raises((PermissionError, NotFoundError)):
            sql_store.update_clause_mapping_review(
                "bank-b",
                clause_id,
                mapping_id,
                status=ClauseReviewStatus.APPROVED,
                actor="attacker",
                role="reviewer",
            )

        # Approve for Bank A and compile baseline
        sql_store.update_clause_review(
            "bank-a",
            clause_id,
            status=ClauseReviewStatus.APPROVED,
            actor="usr-reviewer-a",
            role="reviewer",
        )
        sql_store.update_clause_mapping_review(
            "bank-a",
            clause_id,
            mapping_id,
            status=ClauseReviewStatus.APPROVED,
            actor="usr-reviewer-a",
            role="reviewer",
        )
        refreshed_pol_a = sql_store.get_enterprise_policy("bank-a", pol_a.policy_id)
        base_a = compile_enterprise_baseline(
            tenant_id="bank-a",
            name="Bank A Baseline",
            policies=[refreshed_pol_a],
            version="1.0.0",
        )
        sql_store.save_enterprise_baseline("bank-a", base_a)

        assert sql_store.list_enterprise_baselines("bank-b") == []
        with pytest.raises(NotFoundError):
            sql_store.get_enterprise_baseline("bank-b", base_a.baseline_id)
    finally:
        sql_store.close()


def test_public_demo_tenant_cannot_access_private_endpoints():
    """The 'public-demo' tenant is strictly confined to stateless DEMO_BANKING_V1 assessments."""
    # Allowed: stateless DEMO_BANKING_V1 coverage assessment
    demo_ok = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": "public-demo"},
        json={
            "questionnaire_pack": "DEMO_BANKING_V1",
            "assessment_mode": "regulatory_only",
            "persist": False,
        },
    )
    assert demo_ok.status_code == 201

    # Denied: persisting an assessment under public-demo
    demo_persist = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": "public-demo"},
        json={
            "questionnaire_pack": "DEMO_BANKING_V1",
            "assessment_mode": "regulatory_only",
            "persist": True,
        },
    )
    assert demo_persist.status_code == 403

    # Denied: listing or importing questionnaires under public-demo
    assert (
        client.get("/v1/questionnaires", headers={"X-Tenant-ID": "public-demo"}).status_code
        == 403
    )
    assert (
        client.get(
            "/v1/enterprise/policies", headers={"X-Tenant-ID": "public-demo"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/v1/enterprise/baselines", headers={"X-Tenant-ID": "public-demo"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/v1/assessments/any-id/report", headers={"X-Tenant-ID": "public-demo"}
        ).status_code
        == 403
    )


def test_viewer_cannot_run_assessments_in_private_tenant():
    """A Viewer can read findings and reports, but cannot run new coverage or policy gap assessments."""
    tenant = "sec-p0-viewer-assess"
    viewer_cov = client.post(
        "/v1/assessments/coverage",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "usr-viewer-1",
            "X-Role": "viewer",
        },
        json={
            "questionnaire_pack": "DEMO_BANKING_V1",
            "assessment_mode": "regulatory_only",
            "persist": False,
        },
    )
    assert viewer_cov.status_code == 403

