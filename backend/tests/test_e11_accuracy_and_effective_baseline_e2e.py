"""E1.1 Accuracy, Effective Baseline Binding & End-to-End Assurance Test Suite.

Covers:
1. Effective Baseline Selection & 8-Property Deterministic Binding Validation:
   - Eliminates blind `eff_baselines[-1]` attachment in `POST /v1/assessments/coverage`.
   - Verifies Tenant ID, Enterprise Baseline ID, Version & Revision, SHA-256 fingerprints,
     Regulatory Pack ID & version, Applicability context (`use_case`), Assessment date
     (`as_of_date`), and Reconciliation Decision review/staleness status.
   - Verifies multiple Effective Baselines across different applicability contexts and
     regulatory versions.
2. Assessment Integration Contract (`assessment_basis` & `effective_baseline_binding_mode`):
   - `"regulatory_pack_only"`, `"regulatory_pack_plus_enterprise_baseline"`, and
     `"effective_assessment_baseline"`.
   - Verifies reconciled equivalence groups, unresolved reconciliation tracking, and
     reconciliation conflict gap generation without inflating confirmed coverage.
3. Realistic Multi-Organisation End-to-End Evaluation Benchmark (Dev + Held-Out Splits):
   - Uses real in-memory PDF, DOCX, and TXT policy documents and multi-layout XLSX
     questionnaires across 4 simulated Australian financial institutions (36 clauses).
   - Evaluates the full pipeline WITHOUT passing ground-truth `external_obligation_id`
     or preassigned canonical `control_facets`.
"""

from __future__ import annotations

import base64
import io
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_aiaf_question_bank, load_regulatory_pack
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import (
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    GapType,
    MappingRelationship,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
)
from banking_crosswalk.policy_documents import extract_policy_file
from banking_crosswalk.reconciliation import (
    compose_effective_assessment_baseline,
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
    review_reconciliation_decision,
    validate_effective_baseline_for_assessment,
    verify_effective_baseline_integrity,
)
from banking_crosswalk.store import store


@pytest.fixture(autouse=True)
def reset_store():
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


@pytest.fixture
def demo_question_bank():
    return load_aiaf_question_bank()


def _pdf_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _build_pdf_bytes(lines: Sequence[str], title: str = "Enterprise Policy Document") -> bytes:
    """Construct a valid, standards-compliant PDF 1.4 document parseable by pypdf strict mode."""
    stream_lines = ["BT", "/F1 10 Tf", "36 750 Td", "14 TL"]
    stream_lines.append(f"({_pdf_escape(title)}) Tj")
    stream_lines.append("T*")
    for line in lines:
        stream_lines.append(f"({_pdf_escape(line)}) Tj")
        stream_lines.append("T*")
    stream_lines.append("ET")
    stream_bytes = ("\n".join(stream_lines) + "\n").encode("latin-1", errors="replace")

    objs: List[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"endstream\nendobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: List[int] = []
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(out)


def _build_docx_bytes(paragraphs: Sequence[str], table_rows: Optional[Sequence[Sequence[str]]] = None) -> bytes:
    """Construct an in-memory .docx file with paragraphs and optional table clauses."""
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_rows:
        cols = max(len(r) for r in table_rows)
        tbl = doc.add_table(rows=len(table_rows), cols=cols)
        for r_idx, row in enumerate(table_rows):
            for c_idx, val in enumerate(row):
                tbl.cell(r_idx, c_idx).text = val
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_xlsx_bytes(
    sheet_name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> bytes:
    """Construct an in-memory .xlsx questionnaire workbook with custom sheet/column layout."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(list(headers))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _create_approved_policy_and_baseline(
    tenant_id: str,
    *,
    policy_name: str = "Enterprise AI Governance Standard",
    policy_version: str = "1.0.0",
    baseline_version: str = "1.0.0",
    revision: int = 1,
    clauses_spec: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[EnterprisePolicy, EnterpriseBaseline]:
    pol_id = f"POL-{uuid.uuid4().hex[:8]}"
    specs = clauses_spec or [
        {
            "text": "An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
            "control_id": "CTRL-PRIV-GOVERNANCE",
            "facets": [
                "privacy_accountability_assigned",
                "privacy_practices_implemented",
                "privacy_policy_current",
            ],
        },
        {
            "text": "All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval.",
            "control_id": "CTRL-HUMAN-OVERSIGHT",
            "facets": ["human_approval_required", "approval_threshold_defined", "pre_execution_block"],
            "thresholds_aud": [500.0],
            "threshold_operator": ">",
            "threshold_currency": "AUD",
            "approval_timing": "pre_execution",
            "required_approval_role": "Authorised Officer",
        },
    ]
    clauses: List[EnterpriseClause] = []
    for idx, sp in enumerate(specs, start=1):
        cid = sp.get("clause_id") or f"CLS-{pol_id}-{idx:02d}"
        ctrl_id = sp.get("control_id")
        facets = list(sp.get("facets") or [])
        mappings: List[ClauseControlMapping] = []
        if ctrl_id:
            mappings.append(
                ClauseControlMapping(
                    mapping_id=f"MAP-{cid}",
                    tenant_id=tenant_id,
                    clause_id=cid,
                    control_id=ctrl_id,
                    relationship=MappingRelationship.FULL,
                    mapped_facets=facets,
                    review_status=sp.get("mapping_status", ClauseReviewStatus.APPROVED),
                    reviewer_actor="reviewer@bank.example",
                    reviewer_role="reviewer",
                )
            )
        clauses.append(
            EnterpriseClause(
                clause_id=cid,
                policy_id=pol_id,
                tenant_id=tenant_id,
                source_name=policy_name,
                text=sp["text"],
                mandatory=sp.get("mandatory", True),
                authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
                review_status=sp.get("clause_status", ClauseReviewStatus.APPROVED),
                control_facets=facets,
                thresholds_aud=list(sp.get("thresholds_aud") or []),
                threshold_operator=sp.get("threshold_operator"),
                threshold_currency=sp.get("threshold_currency"),
                approval_timing=sp.get("approval_timing"),
                required_approval_role=sp.get("required_approval_role"),
                is_conditional=sp.get("is_conditional", False),
                condition_description=sp.get("condition_description"),
                has_exception_clause=sp.get("has_exception_clause", False),
                exception_description=sp.get("exception_description"),
                is_unmapped=(ctrl_id is None),
                control_mappings=mappings,
            )
        )

    policy = EnterprisePolicy(
        policy_id=pol_id,
        tenant_id=tenant_id,
        name=policy_name,
        version=policy_version,
        clauses=clauses,
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant_id,
        name=f"{policy_name} Baseline",
        policies=[policy],
        version=baseline_version,
        revision=revision,
    )
    store.save_enterprise_policy(tenant_id, policy)
    store.save_enterprise_baseline(tenant_id, baseline)
    return policy, baseline


# ═════════════════════════════════════════════════════════════════════════════
# PART 1: EFFECTIVE BASELINE SELECTION & 8-PROPERTY BINDING VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

def test_e11_01_no_blind_latest_effective_baseline_attachment_when_omitted(client):
    """Verify that POST /v1/assessments/coverage NEVER auto-attaches eff_baselines[-1]
    merely because an EffectiveAssessmentBaseline exists for the same enterprise_baseline_id.
    """
    tenant = f"t-e11-01-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(tenant)

    # Compose and persist an Effective Assessment Baseline for this enterprise baseline
    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"as_of_date": "2026-11-02"},
    )
    assert eff_res.status_code == 201
    stored_eff_id = eff_res.json()["effective_baseline_id"]
    assert len(store.list_effective_baselines(tenant, baseline_id=baseline.baseline_id)) == 1

    # Run coverage assessment WITHOUT specifying effective_baseline_id
    cov_res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert cov_res.status_code == 201
    body = cov_res.json()
    assert body["effective_baseline_id"] is None, (
        f"Expected effective_baseline_id=None when not requested, but got {body['effective_baseline_id']} (stored was {stored_eff_id})"
    )
    assert body["effective_baseline_sha256"] is None
    assert body["assessment_basis"] == "regulatory_pack_plus_enterprise_baseline"
    assert body["effective_baseline_binding_mode"] == "not_bound"


def test_e11_02_explicit_effective_baseline_selection_among_multiple_use_case_contexts(client):
    """When multiple Effective Baselines exist for the same enterprise_baseline_id under
    different applicability contexts (e.g., Domestic Refund Agent vs Cross-Border Credit Agent),
    binding the matching one succeeds while binding the non-matching latest one (`eff_baselines[-1]`)
    fails closed with 409 Conflict.
    """
    tenant = f"t-e11-02-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(tenant)

    uc_domestic_refund = BankingUseCase(
        name="Domestic Refund Assistant",
        entity_type="ADI",
        apra_regulated=True,
        handles_personal_information=True,
        cross_border_disclosure=False,
        assists_consumer_credit_decision=False,
        credit_licensee_or_credit_activity=False,
        handles_regulated_complaints=True,
        idr_obligations=True,
        approval_threshold_aud=250.0,
    )
    uc_cross_border_credit = BankingUseCase(
        name="Offshore Credit Underwriting Model",
        entity_type="ADI",
        apra_regulated=True,
        handles_personal_information=True,
        cross_border_disclosure=True,
        assists_consumer_credit_decision=True,
        credit_licensee_or_credit_activity=True,
        handles_regulated_complaints=False,
        idr_obligations=False,
        approval_threshold_aud=250.0,
    )

    # 1. Compose Effective Baseline 1 for domestic refund use case
    res_eff_dom = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"use_case": uc_domestic_refund.model_dump(mode="json"), "as_of_date": "2026-11-02"},
    )
    assert res_eff_dom.status_code == 201
    eff_dom = res_eff_dom.json()

    # 2. Compose Effective Baseline 2 (which becomes eff_baselines[-1]!) for cross-border credit use case
    res_eff_cb = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"use_case": uc_cross_border_credit.model_dump(mode="json"), "as_of_date": "2026-11-02"},
    )
    assert res_eff_cb.status_code == 201
    eff_cb = res_eff_cb.json()
    assert eff_dom["effective_baseline_id"] != eff_cb["effective_baseline_id"]

    # Attempting to bind eff_cb (eff_baselines[-1]) to a domestic refund assessment MUST fail with 409
    bad_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_cb["effective_baseline_id"],
            "use_case": uc_domestic_refund.model_dump(mode="json"),
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert bad_cov.status_code == 409
    assert "applicability context mismatch" in bad_cov.json()["detail"].lower()

    # Explicitly binding eff_dom to the domestic refund assessment succeeds
    ok_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_dom["effective_baseline_id"],
            "effective_baseline_sha256": eff_dom["effective_baseline_sha256"],
            "use_case": uc_domestic_refund.model_dump(mode="json"),
            "questionnaire_pack": "DEMO_BANKING_V1",
            "as_of_date": "2026-11-02",
        },
    )
    assert ok_cov.status_code == 201
    ok_body = ok_cov.json()
    assert ok_body["effective_baseline_id"] == eff_dom["effective_baseline_id"]
    assert ok_body["effective_baseline_sha256"] == eff_dom["effective_baseline_sha256"]
    assert ok_body["assessment_basis"] == "effective_assessment_baseline"
    assert ok_body["effective_baseline_binding_mode"] == "explicit_validated_effective_baseline"


def test_e11_03_rejects_effective_baseline_with_mismatched_regulatory_pack_version(
    client, regulatory_pack
):
    """Multiple Effective Baselines composed against different regulatory pack versions:
    an Effective Baseline composed against '0.0.9-prior' must be rejected when the
    active assessment runs against '0.1.0'.
    """
    tenant = f"t-e11-03-{uuid.uuid4().hex[:6]}"
    policy, baseline = _create_approved_policy_and_baseline(tenant)
    uc = BankingUseCase.enterprise_baseline()

    old_reg_pack = regulatory_pack.model_copy(update={"version": "0.0.9-prior"})
    eff_old = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=old_reg_pack,
        use_case=uc,
        enterprise_baseline=baseline,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    store.save_effective_baseline(tenant, eff_old)

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_old.effective_baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res.status_code == 409
    assert "regulatory_pack_version mismatch" in res.json()["detail"]


def test_e11_04_rejects_effective_baseline_with_mismatched_enterprise_baseline_version_or_revision(
    client, regulatory_pack
):
    """An Effective Baseline composed for revision 1 ('1.0.0') must not be bound to an
    assessment evaluating revision 2 ('1.1.0') or a different enterprise_baseline_id.
    """
    tenant = f"t-e11-04-{uuid.uuid4().hex[:6]}"
    policy, baseline_v1 = _create_approved_policy_and_baseline(
        tenant, baseline_version="1.0.0", revision=1
    )
    uc = BankingUseCase.enterprise_baseline()
    eff_v1 = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        enterprise_baseline=baseline_v1,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    store.save_effective_baseline(tenant, eff_v1)

    # Compile a second baseline (v1.1.0, revision 2)
    baseline_v2 = compile_enterprise_baseline(
        tenant_id=tenant,
        name=baseline_v1.name,
        policies=[policy],
        version="1.1.0",
        revision=2,
    )
    store.save_enterprise_baseline(tenant, baseline_v2)

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline_v2.baseline_id,
            "effective_baseline_id": eff_v1.effective_baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res.status_code == 409
    assert "enterprise_baseline_id mismatch" in res.json()["detail"]

    # Also test same baseline_id with mismatched version/revision on EffectiveAssessmentBaseline
    baseline_v2_rev1 = compile_enterprise_baseline(
        tenant_id=tenant,
        baseline_id=baseline_v2.baseline_id,
        name=baseline_v1.name,
        policies=[policy],
        version="1.1.0",
        revision=1,
    )
    eff_wrong_rev = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        enterprise_baseline=baseline_v2_rev1,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    store.save_effective_baseline(tenant, eff_wrong_rev)

    res_rev = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline_v2.baseline_id,
            "effective_baseline_id": eff_wrong_rev.effective_baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res_rev.status_code == 409
    assert "enterprise_baseline_revision mismatch" in res_rev.json()["detail"]


def test_e11_05_rejects_effective_baseline_with_tampered_or_mismatched_sha256(
    client, regulatory_pack
):
    """Verify both caller-supplied SHA-256 pinning and cryptographic payload integrity verification."""
    tenant = f"t-e11-05-{uuid.uuid4().hex[:6]}"
    policy, baseline = _create_approved_policy_and_baseline(tenant)
    uc = BankingUseCase.enterprise_baseline()
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=uc,
        enterprise_baseline=baseline,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    assert verify_effective_baseline_integrity(eff) is True
    store.save_effective_baseline(tenant, eff)

    # 1. Caller supplies wrong expected SHA-256 pin -> 409 Conflict
    res_pin = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff.effective_baseline_id,
            "effective_baseline_sha256": "0" * 64,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res_pin.status_code == 409
    assert "sha-256 mismatch" in res_pin.json()["detail"].lower()

    # 2. Stored EffectiveBaseline content is tampered without updating SHA-256 -> 422 Integrity Error
    tampered = eff.model_copy(
        update={
            "effective_baseline_id": eff.effective_baseline_id,
            "applicable_external_obligation_ids": eff.applicable_external_obligation_ids[:-1],
        }
    )
    assert verify_effective_baseline_integrity(tampered) is False
    store.save_effective_baseline(tenant, tampered)

    res_tampered = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": tampered.effective_baseline_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res_tampered.status_code == 422
    assert "integrity error" in res_tampered.json()["detail"].lower()


def test_e11_06_rejects_effective_baseline_with_mismatched_as_of_date(client):
    """An Effective Baseline composed for as_of_date '2026-11-02' must be rejected when
    an assessment explicitly requests as_of_date '2026-12-31'.
    """
    tenant = f"t-e11-06-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(tenant)

    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"as_of_date": "2026-11-02"},
    )
    assert eff_res.status_code == 201
    eff_id = eff_res.json()["effective_baseline_id"]

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_id,
            "as_of_date": "2026-12-31",
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res.status_code == 409
    assert "as_of_date mismatch" in res.json()["detail"]


def test_e11_07_rejects_effective_baseline_when_reconciliation_becomes_stale_or_review_changes(
    client,
):
    """If a reconciliation decision is approved or a policy is superseded AFTER an
    EffectiveAssessmentBaseline was composed, binding that stale EffectiveAssessmentBaseline
    to an assessment must fail closed with 409 Conflict until re-composed.
    """
    tenant = f"t-e11-07-{uuid.uuid4().hex[:6]}"
    policy, baseline = _create_approved_policy_and_baseline(tenant)

    # 1. Reconcile baseline (decisions start in 'proposed')
    rec_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/reconcile",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
    )
    assert rec_res.status_code == 201
    decisions = rec_res.json()
    eq_rec = next(
        d for d in decisions if d["validated_relationship"] == "equivalent"
    )

    # 2. Compose Effective Baseline BEFORE approving the reconciliation decision
    eff_before_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"as_of_date": "2026-11-02"},
    )
    assert eff_before_res.status_code == 201
    eff_before_id = eff_before_res.json()["effective_baseline_id"]

    # 3. Reviewer now approves eq_rec
    rev_res = client.put(
        f"/v1/enterprise/reconciliations/{eq_rec['reconciliation_id']}/review",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={
            "decision_status": "approved",
            "actor": "rev.1",
            "role": "reviewer",
            "comment": "Approved APP 1 equivalence.",
        },
    )
    assert rev_res.status_code == 200

    # 4. Attempting to bind eff_before_id (which does not include the newly approved reconciliation) fails with 409
    stale_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_before_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert stale_cov.status_code == 409
    assert "stale relative to current approved reconciliation decisions" in stale_cov.json()["detail"]

    # 5. Re-compose Effective Baseline -> now binding succeeds!
    eff_after_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"as_of_date": "2026-11-02"},
    )
    assert eff_after_res.status_code == 201
    eff_after_id = eff_after_res.json()["effective_baseline_id"]

    ok_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_after_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert ok_cov.status_code == 201
    assert ok_cov.json()["effective_baseline_id"] == eff_after_id

    # 6. Now mark the underlying policy as superseded -> reconciliation decisions become stale -> binding eff_after_id fails with 409
    store.save_enterprise_policy(
        tenant, policy.model_copy(update={"status": "superseded"})
    )
    superseded_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff_after_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert superseded_cov.status_code == 409
    assert "stale" in superseded_cov.json()["detail"].lower()


def test_e11_08_rejects_effective_baseline_in_regulatory_only_mode(client):
    """Providing effective_baseline_id when assessment_mode='regulatory_only' must return 400."""
    tenant = f"t-e11-08-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(tenant)
    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
    )
    eff_id = eff_res.json()["effective_baseline_id"]

    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "regulatory_only",
            "effective_baseline_id": eff_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert res.status_code == 400
    assert "regulatory_only" in res.json()["detail"]


def test_e11_09_bound_effective_baseline_integrates_equivalence_groups_unresolved_and_conflict_gaps(
    client,
):
    """When a valid EffectiveAssessmentBaseline is bound to a CoverageAssessment:
    - `reconciled_equivalence_group_ids` captures reviewed equivalence groups while
      retaining all external obligations in `results`.
    - `unresolved_reconciliation_ids` records pending/unresolved reconciliations.
    - `reconciliation_conflict_gaps` and `gaps` surface `GapRecord` items for
      `potential_conflict` and `weaker_or_potentially_insufficient` clauses.
    """
    tenant = f"t-e11-09-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(
        tenant,
        clauses_spec=[
            {
                "clause_id": "CLS-APP1-EQ",
                "text": "An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
                "control_id": "CTRL-PRIV-GOVERNANCE",
                "facets": [
                    "privacy_accountability_assigned",
                    "privacy_practices_implemented",
                    "privacy_policy_current",
                ],
            },
            {
                "clause_id": "CLS-CPS234-CONFLICT",
                "text": "Material AI information security incidents must be notified to APRA within 14 days after internal review.",
                "control_id": "CTRL-SEC-INCIDENT",
                "facets": ["apra_notification_screened"],
            },
        ],
    )

    rec_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/reconcile",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
    )
    assert rec_res.status_code == 201
    decisions = rec_res.json()
    eq_dec = next(
        d
        for d in decisions
        if d["enterprise_clause_id"] == "CLS-APP1-EQ"
        and d["external_obligation_id"] == "AU-PRIV-APP1-GOV"
    )
    conflict_dec = next(
        d
        for d in decisions
        if d["enterprise_clause_id"] == "CLS-CPS234-CONFLICT"
        and d["external_obligation_id"] == "AU-APRA-CPS234-INCIDENT"
    )
    assert conflict_dec["validated_relationship"] == "potential_conflict"

    # Approve the APP 1 equivalence decision
    client.put(
        f"/v1/enterprise/reconciliations/{eq_dec['reconciliation_id']}/review",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={
            "decision_status": "approved",
            "actor": "rev.1",
            "role": "reviewer",
            "comment": "Confirmed APP 1 equivalence.",
        },
    )

    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
        json={"as_of_date": "2026-11-02"},
    )
    assert eff_res.status_code == 201
    eff = eff_res.json()

    cov_res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff["effective_baseline_id"],
            "effective_baseline_sha256": eff["effective_baseline_sha256"],
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert cov_res.status_code == 201, cov_res.text
    assessment = cov_res.json()

    assert assessment["assessment_basis"] == "effective_assessment_baseline"
    assert assessment["effective_baseline_binding_mode"] == "explicit_validated_effective_baseline"
    assert "GRP-EQ-AU-PRIV-APP1-GOV-CLS-APP1-EQ" in assessment["reconciled_equivalence_group_ids"]
    assert conflict_dec["reconciliation_id"] in assessment["unresolved_reconciliation_ids"]
    assert len(assessment["reconciliation_conflict_gaps"]) >= 1
    conflict_gap = assessment["reconciliation_conflict_gaps"][0]
    assert conflict_gap["source_type"] == "reconciliation_conflict"
    assert conflict_gap["policy_clause_id"] == "CLS-CPS234-CONFLICT"
    assert conflict_gap["obligation_id"] == "AU-APRA-CPS234-INCIDENT"
    assert conflict_gap["severity"] == "critical"

    # External obligation AU-PRIV-APP1-GOV is still preserved in results (never silently removed)
    result_ob_ids = {r["obligation_id"] for r in assessment["results"]}
    assert "AU-PRIV-APP1-GOV" in result_ob_ids
    assert "AU-APRA-CPS234-INCIDENT" in result_ob_ids


def test_e11_10_bound_effective_baseline_never_inflates_confirmed_coverage_rate(
    client,
):
    """Binding an EffectiveAssessmentBaseline with approved equivalence groups must NEVER
    mark an external obligation as confirmed COVERED unless the questionnaire itself has
    human-approved question-to-facet mappings.
    """
    tenant = f"t-e11-10-{uuid.uuid4().hex[:6]}"
    _, baseline = _create_approved_policy_and_baseline(tenant)

    rec_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/reconcile",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
    )
    for d in rec_res.json():
        if d["validated_relationship"] == "equivalent":
            client.put(
                f"/v1/enterprise/reconciliations/{d['reconciliation_id']}/review",
                headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
                json={
                    "decision_status": "approved",
                    "actor": "rev.1",
                    "role": "reviewer",
                    "comment": "Approved equivalence.",
                },
            )

    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant, "X-Actor": "rev.1", "X-Role": "reviewer"},
    )
    eff = eff_res.json()

    cov_res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.1", "X-Role": "analyst"},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline.baseline_id,
            "effective_baseline_id": eff["effective_baseline_id"],
            "questionnaire_pack": "DEMO_BANKING_V1",
        },
    )
    assert cov_res.status_code == 201
    metrics = cov_res.json()["metrics"]
    assert metrics["confirmed_covered"] == 0
    assert metrics["confirmed_coverage_rate"] == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# PART 2: REALISTIC MULTI-ORGANISATION END-TO-END EVALUATION BENCHMARK
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LabelledBenchmarkClause:
    case_id: str
    split: str  # "dev" or "held_out"
    org_id: str
    doc_filename: str
    doc_format: str  # "pdf", "docx", "txt"
    raw_text: str
    phenomenon: str
    ground_truth_obligation_id: Optional[str]
    ground_truth_relationship: ReconciliationRelationship
    expects_human_resolution: bool


E11_BENCHMARK_CLAUSES: Tuple[LabelledBenchmarkClause, ...] = (
    # ─────────────────────────────────────────────────────────────────────────
    # DEVELOPMENT SPLIT (18 clauses across 2 organisations, PDF + DOCX + TXT)
    # ─────────────────────────────────────────────────────────────────────────
    # Org 1 (Dev): Southern Cross Retail Bank — PDF policy + TXT addendum
    LabelledBenchmarkClause(
        case_id="DEV-SCB-01",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_ai_governance_policy.pdf",
        doc_format="pdf",
        raw_text="Each AI system must have an accountable privacy owner assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        phenomenon="equivalent_canonical_terminology",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-02",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_ai_governance_policy.pdf",
        doc_format="pdf",
        raw_text="The bank must publish a current privacy policy describing personal information handling for retail digital channels.",
        phenomenon="incomplete_single_facet_requirement",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-03",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_ai_governance_policy.pdf",
        doc_format="pdf",
        raw_text="Before disclosing customer data to an overseas recipient in a cross-border cloud region, APP 8 contractual privacy clauses must be executed and 16C cross-border disclosure accountability must be confirmed.",
        phenomenon="equivalent_cross_border_app8",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-04",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_ai_governance_policy.pdf",
        doc_format="pdf",
        raw_text="Material AI information security incidents must have incident detection, escalation, material weakness tracking, and APRA notification completed within 24 hours.",
        phenomenon="stricter_timeframe_24h_vs_72h",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-05",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_ai_governance_policy.pdf",
        doc_format="pdf",
        raw_text="Material AI information security incidents must be notified to APRA within 14 days following internal forensic sign-off.",
        phenomenon="conflicting_timeframe_14d_vs_72h",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-06",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_delegations_addendum.txt",
        doc_format="txt",
        raw_text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer human approval before payment execution.",
        phenomenon="stricter_numeric_threshold_aud_500",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-07",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_delegations_addendum.txt",
        doc_format="txt",
        raw_text="All automated customer refund decisions above USD 500 must obtain pre-execution Authorised Officer human approval before payment execution.",
        phenomenon="currency_mismatch_usd_vs_aud",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-08",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_delegations_addendum.txt",
        doc_format="txt",
        raw_text="Low-value sandbox AI experiments do not require human approval or APP 8 cross-border contractual privacy safeguards.",
        phenomenon="negative_exemption_does_not_require",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-SCB-09",
        split="dev",
        org_id="southern-cross-bank",
        doc_filename="southern_cross_delegations_addendum.txt",
        doc_format="txt",
        raw_text="First Nations acoustic dialect consultation must be completed prior to deploying regional voice assistant models.",
        phenomenon="unmapped_domain_specific_requirement",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
    ),
    # Org 2 (Dev): Pacific Mutual Credit Union — DOCX standard + TXT privacy ops
    LabelledBenchmarkClause(
        case_id="DEV-PMC-10",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_credit_ai_standard.docx",
        doc_format="docx",
        raw_text="Before collecting personal or sensitive information for AI credit scoring, the collection purpose must be defined, data minimisation necessity assessed, and explicit consent obtained for sensitive information.",
        phenomenon="equivalent_app3_collection",
        ground_truth_obligation_id="AU-PRIV-APP3-COLLECT",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-11",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_credit_ai_standard.docx",
        doc_format="docx",
        raw_text="Where customer training records exceed 100,000 accounts, an accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        phenomenon="conditional_clause_narrowing_scope",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-12",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_credit_ai_standard.docx",
        doc_format="docx",
        raw_text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained, unless waived by a business unit head.",
        phenomenon="exception_clause_weakening_obligation",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-13",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_credit_ai_standard.docx",
        doc_format="docx",
        raw_text="Consumer credit AI models must complete an unsuitability assessment under NCCP s 128, verify the consumer financial situation, and inquire into consumer requirements and objectives.",
        phenomenon="equivalent_nccp_s128_lending",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-14",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_credit_ai_standard.docx",
        doc_format="docx",
        raw_text="Automated credit decline letters must be eyeballed by a lending specialist before dispatch to the borrower.",
        phenomenon="colloquial_paraphrase_missing_lexical_facets",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-15",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_privacy_ops.txt",
        doc_format="txt",
        raw_text="All LLM prompts and model outputs must be recorded via prompt logging in the immutable telemetry vault for 7 years.",
        phenomenon="additional_enterprise_requirement_prompt_logging",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-16",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_privacy_ops.txt",
        doc_format="txt",
        raw_text="Appropriate governance arrangements shall be applied as determined from time to time in accordance with Schedule B.",
        phenomenon="ambiguous_unclear_applicability",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-17",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_privacy_ops.txt",
        doc_format="txt",
        raw_text="External foundation model APIs must enforce zero data retention so customer prompts are never retained by the vendor.",
        phenomenon="additional_or_stricter_zero_retention",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="DEV-PMC-18",
        split="dev",
        org_id="pacific-mutual-cu",
        doc_filename="pacific_mutual_privacy_ops.txt",
        doc_format="txt",
        raw_text="GPU cluster workload schedulers must tag carbon-intensity megawatt telemetry prior to batch inference runs.",
        phenomenon="unmapped_esg_compute_telemetry",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # HELD-OUT TEST SPLIT (18 clauses across 2 organisations, PDF + DOCX + TXT)
    # ─────────────────────────────────────────────────────────────────────────
    # Org 3 (Held-Out): Tasman Institutional Bank — PDF policy + DOCX cyber standard
    LabelledBenchmarkClause(
        case_id="HO-TIB-01",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_institutional_ai_policy.pdf",
        doc_format="pdf",
        raw_text="For every AI system, an accountable privacy owner must be assigned, privacy practices and privacy impact assessments implemented, and a current privacy policy maintained.",
        phenomenon="equivalent_app1_full",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-02",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_institutional_ai_policy.pdf",
        doc_format="pdf",
        raw_text="Before any offshore cloud AI transfer, overseas recipients and data residency regions must be mapped, APP 8 contractual privacy clauses executed, and 16C cross-border disclosure accountability assessed.",
        phenomenon="equivalent_app8_full",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-03",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_institutional_ai_policy.pdf",
        doc_format="pdf",
        raw_text="Offshore GenAI model telemetry must stay on-shore in Australian data centres unless the CISO signs a sovereignty waiver.",
        phenomenon="paraphrased_sovereignty_with_exception_waiver",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-04",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_institutional_ai_policy.pdf",
        doc_format="pdf",
        raw_text="All automated customer refund decisions of at least AUD 250 must obtain dual human sign-off prior to execution.",
        phenomenon="stricter_dual_approval_and_gte_operator",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-05",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_institutional_ai_policy.pdf",
        doc_format="pdf",
        raw_text="Automated customer refund decisions above AUD 500 may execute automatically subject to post-execution review by a team leader.",
        phenomenon="weaker_post_execution_and_discretionary_modality",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-06",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_cyber_incident_standard.docx",
        doc_format="docx",
        raw_text="Information security capability under CPS 234 must be commensurate with threats, third-party security controls assured, and security control testing conducted regularly.",
        phenomenon="partial_or_equivalent_cps234_security",
        ground_truth_obligation_id="AU-APRA-CPS234-CONTROLS",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-07",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_cyber_incident_standard.docx",
        doc_format="docx",
        raw_text="Material CPS 234 information security incidents affecting AI systems must be notified to APRA within 10 days of board briefing.",
        phenomenon="conflicting_cps234_10_day_deadline",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-08",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_cyber_incident_standard.docx",
        doc_format="docx",
        raw_text="Customer personal information held in AI vector indices must have information security controls, an approved retention period, and verified de-identify or destroy procedures under APP 11.",
        phenomenon="equivalent_app11_security_retention",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-TIB-09",
        split="held_out",
        org_id="tasman-institutional-bank",
        doc_filename="tasman_cyber_incident_standard.docx",
        doc_format="docx",
        raw_text="Personal records stored in AI logs must support APP 12 access request retrieval and APP 13 correction propagation within 30 days.",
        phenomenon="equivalent_app12_13_access_correction",
        ground_truth_obligation_id="AU-PRIV-APP12-13-RIGHTS",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    # Org 4 (Held-Out): Aurora Digital Neobank — DOCX guardrails + TXT dispute/credit policy
    LabelledBenchmarkClause(
        case_id="HO-ADN-10",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_neobank_genai_guardrails.docx",
        doc_format="docx",
        raw_text="At collection or before collection of customer personal information by the AI assistant, a privacy notice must be presented with complete purpose of collection and disclosure notice content under APP 5.",
        phenomenon="equivalent_app5_collection_notice",
        ground_truth_obligation_id="AU-PRIV-APP5-NOTICE",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-11",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_neobank_genai_guardrails.docx",
        doc_format="docx",
        raw_text="Where secondary use of customer transcripts is proposed for fine-tuning, primary purpose must be recorded, secondary use consent checked, and a disclosure log maintained under APP 6.",
        phenomenon="conditional_app6_use_disclosure",
        ground_truth_obligation_id="AU-PRIV-APP6-USE",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-12",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_neobank_genai_guardrails.docx",
        doc_format="docx",
        raw_text="Internal productivity chatbots do not require privacy notice or APP 5 collection notice disclosures.",
        phenomenon="negative_exemption_app5_conflict",
        ground_truth_obligation_id="AU-PRIV-APP5-NOTICE",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-13",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_neobank_genai_guardrails.docx",
        doc_format="docx",
        raw_text="All production AI models must be registered in the enterprise model inventory with quarterly bias testing and algorithmic bias fairness reports.",
        phenomenon="enterprise_model_inventory_and_bias_testing",
        ground_truth_obligation_id="AU-ASIC-REP798-AI-GAP",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-14",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_dispute_and_credit_policy.txt",
        doc_format="txt",
        raw_text="Automated complaint triage under RG 271 internal dispute resolution must track IDR maximum timeframe compliance, monitor automated complaint handling, and escalate systemic issues.",
        phenomenon="paraphrased_rg271_idr_complaint_handling",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-15",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_dispute_and_credit_policy.txt",
        doc_format="txt",
        raw_text="All automated customer refund decisions above EUR 1,000 must obtain pre-execution Senior Manager human approval before payment execution.",
        phenomenon="currency_mismatch_eur_vs_aud",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-16",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_dispute_and_credit_policy.txt",
        doc_format="txt",
        raw_text="Reasonable governance steps shall be taken where appropriate as determined from time to time under Schedule D.",
        phenomenon="ambiguous_schedule_d_clause",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-17",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_dispute_and_credit_policy.txt",
        doc_format="txt",
        raw_text="Pre-execution human approval blocking for refunds above AUD 500 is required by policy, but the automated blocking workflow is currently not implemented in the mobile app.",
        phenomenon="missing_implementation_evidence_unimplemented",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
    ),
    LabelledBenchmarkClause(
        case_id="HO-ADN-18",
        split="held_out",
        org_id="aurora-digital-neobank",
        doc_filename="aurora_dispute_and_credit_policy.txt",
        doc_format="txt",
        raw_text="Mobile UI dark-mode contrast ratios must be verified against WCAG 2.2 AA accessibility tokens before quarterly app store release.",
        phenomenon="unmapped_ui_accessibility_clause",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
    ),
)


def _evaluate_split_end_to_end(
    split_name: str,
    clauses: Sequence[LabelledBenchmarkClause],
    client: TestClient,
    regulatory_pack: Any,
) -> Dict[str, Any]:
    """Run the full end-to-end pipeline on a benchmark split WITHOUT passing
    ground-truth obligation IDs or preassigned control facets.
    """
    by_org_and_doc: Dict[Tuple[str, str, str], List[LabelledBenchmarkClause]] = {}
    for item in clauses:
        by_org_and_doc.setdefault(
            (item.org_id, item.doc_filename, item.doc_format), []
        ).append(item)

    total_expected_clauses = len(clauses)
    extracted_matched_count = 0
    citation_traceable_count = 0

    retrieval_queries = 0
    recall_at_1_hits = 0
    recall_at_5_hits = 0

    y_true: List[str] = []
    y_pred: List[str] = []
    false_equivalences = 0
    false_conflicts = 0
    expected_human_res_total = 0
    expected_human_res_flagged = 0
    false_confirmed_coverage_count = 0
    case_records: List[Dict[str, Any]] = []

    orgs = sorted({c.org_id for c in clauses})
    for org_id in orgs:
        tenant_id = f"e11-{split_name}-{org_id}-{uuid.uuid4().hex[:4]}"
        org_docs = [
            k for k in by_org_and_doc.keys() if k[0] == org_id
        ]
        uploaded_policy_ids: List[str] = []
        extracted_clause_by_case_id: Dict[str, EnterpriseClause] = {}

        for _, filename, fmt in org_docs:
            doc_cases = by_org_and_doc[(org_id, filename, fmt)]
            raw_lines = [c.raw_text for c in doc_cases]
            if fmt == "pdf":
                file_bytes = _build_pdf_bytes(raw_lines, title=f"{org_id} Policy")
            elif fmt == "docx":
                file_bytes = _build_docx_bytes(raw_lines)
            else:
                file_bytes = ("\n\n".join(raw_lines) + "\n").encode("utf-8")

            upload_res = client.post(
                "/v1/enterprise/policies/import-file",
                headers={"X-Tenant-ID": tenant_id, "X-Actor": "analyst.1", "X-Role": "analyst"},
                json={
                    "filename": filename,
                    "file_base64": base64.b64encode(file_bytes).decode("ascii"),
                    "name": filename,
                    "category": "ai_governance",
                    "authority_level": "enterprise_policy",
                    "version": "1.0.0",
                },
            )
            assert upload_res.status_code == 201, upload_res.text
            pol = EnterprisePolicy.model_validate(upload_res.json())
            uploaded_policy_ids.append(pol.policy_id)

            # Approve all extracted clauses (and any proposed control mappings emitted by extractor)
            for ext_cls in pol.clauses:
                client.put(
                    f"/v1/enterprise/clauses/{ext_cls.clause_id}/review",
                    headers={"X-Tenant-ID": tenant_id, "X-Actor": "rev.1", "X-Role": "reviewer"},
                    json={
                        "status": "approved",
                        "actor": "rev.1",
                        "role": "reviewer",
                        "review_comment": "Approved extracted clause for E2E evaluation.",
                    },
                )
                for m in ext_cls.control_mappings or []:
                    client.put(
                        f"/v1/enterprise/clauses/{ext_cls.clause_id}/mappings/{m.mapping_id}/review",
                        headers={"X-Tenant-ID": tenant_id, "X-Actor": "rev.1", "X-Role": "reviewer"},
                        json={
                            "status": "approved",
                            "actor": "rev.1",
                            "role": "reviewer",
                            "review_comment": "Approved extractor candidate control mapping.",
                        },
                    )

            refreshed_pol = store.get_enterprise_policy(tenant_id, pol.policy_id)
            for case in doc_cases:
                # Match extracted clause by full normalized text first to avoid prefix collisions
                norm_full = " ".join(case.raw_text.lower().split())
                matched = next(
                    (
                        c
                        for c in refreshed_pol.clauses
                        if " ".join(c.text.lower().split()) == norm_full
                    ),
                    None,
                )
                if matched is None:
                    matched = next(
                        (
                            c
                            for c in refreshed_pol.clauses
                            if norm_full in " ".join(c.text.lower().split())
                        ),
                        None,
                    )
                if matched is not None:
                    extracted_matched_count += 1
                    extracted_clause_by_case_id[case.case_id] = matched

                # Evaluate Stage A candidate ranking (Recall@1 and Recall@5) WITHOUT target obligation ID
                if matched is not None and case.ground_truth_obligation_id is not None:
                    retrieval_queries += 1
                    ranked = rank_reconciliation_candidates_for_clause(
                        matched,
                        regulatory_pack=regulatory_pack,
                        top_k=5,
                    )
                    top_ids = [r["obligation_id"] for r in ranked]
                    if top_ids and top_ids[0] == case.ground_truth_obligation_id:
                        recall_at_1_hits += 1
                    if case.ground_truth_obligation_id in top_ids[:5]:
                        recall_at_5_hits += 1

        # Compile EnterpriseBaseline for this organisation
        bl_res = client.post(
            "/v1/enterprise/baselines",
            headers={"X-Tenant-ID": tenant_id, "X-Actor": "rev.1", "X-Role": "reviewer"},
            json={
                "name": f"{org_id} Baseline",
                "policy_ids": uploaded_policy_ids,
                "version": "1.0.0",
                "status": "active",
            },
        )
        assert bl_res.status_code == 201
        baseline_id = bl_res.json()["baseline_id"]

        # Run Stage A + Stage B reconciliation via API
        rec_res = client.post(
            f"/v1/enterprise/baselines/{baseline_id}/reconcile",
            headers={"X-Tenant-ID": tenant_id, "X-Actor": "analyst.1", "X-Role": "analyst"},
        )
        assert rec_res.status_code == 201
        org_decisions = rec_res.json()

        org_cases = [c for c in clauses if c.org_id == org_id]
        for case in org_cases:
            ext_cls = extracted_clause_by_case_id.get(case.case_id)
            assert ext_cls is not None, f"Clause {case.case_id} failed document extraction"

            clause_decs = [
                d
                for d in org_decisions
                if d["enterprise_clause_id"] == ext_cls.clause_id
                and d.get("peer_enterprise_clause_id") is None
            ]
            # Select the decision matching ground_truth_obligation_id if retrieved, otherwise the primary decision
            chosen_dec = None
            if case.ground_truth_obligation_id is not None:
                chosen_dec = next(
                    (
                        d
                        for d in clause_decs
                        if d["external_obligation_id"] == case.ground_truth_obligation_id
                    ),
                    None,
                )
            if chosen_dec is None and clause_decs:
                chosen_dec = clause_decs[0]

            assert chosen_dec is not None
            pred_rel = chosen_dec["validated_relationship"]
            true_rel = case.ground_truth_relationship.value

            y_true.append(true_rel)
            y_pred.append(pred_rel)

            if pred_rel == "equivalent" and true_rel != "equivalent":
                false_equivalences += 1
            if pred_rel == "potential_conflict" and true_rel != "potential_conflict":
                false_conflicts += 1

            is_flagged_for_human = (
                chosen_dec["decision_status"] in {"needs_review", "proposed"}
                and (
                    pred_rel
                    in {
                        "potential_conflict",
                        "weaker_or_potentially_insufficient",
                        "undetermined",
                        "unmapped_no_reliable_relationship",
                    }
                    or bool(chosen_dec.get("uncertainties"))
                )
            )
            if case.expects_human_resolution:
                expected_human_res_total += 1
                if is_flagged_for_human:
                    expected_human_res_flagged += 1

            if (
                chosen_dec["enterprise_clause_id"] == ext_cls.clause_id
                and chosen_dec["enterprise_baseline_id"] == baseline_id
                and chosen_dec["regulatory_pack_version"] == regulatory_pack.version
                and len(chosen_dec.get("supporting_passages") or []) >= 1
            ):
                citation_traceable_count += 1

            # Reviewer approves safe non-conflict / non-undetermined decisions for Effective Baseline composition
            if pred_rel in {
                "equivalent",
                "stricter_enterprise_requirement",
                "partially_overlapping",
                "additional_enterprise_requirement",
            } and not case.expects_human_resolution:
                client.put(
                    f"/v1/enterprise/reconciliations/{chosen_dec['reconciliation_id']}/review",
                    headers={"X-Tenant-ID": tenant_id, "X-Actor": "rev.1", "X-Role": "reviewer"},
                    json={
                        "decision_status": "approved",
                        "actor": "rev.1",
                        "role": "reviewer",
                        "comment": f"Approved {pred_rel} in E2E evaluation.",
                    },
                )

            case_records.append(
                {
                    "case_id": case.case_id,
                    "org_id": case.org_id,
                    "doc_format": case.doc_format,
                    "phenomenon": case.phenomenon,
                    "ground_truth_obligation_id": case.ground_truth_obligation_id,
                    "matched_obligation_id": chosen_dec["external_obligation_id"],
                    "ground_truth_relationship": true_rel,
                    "predicted_relationship": pred_rel,
                    "correct": pred_rel == true_rel,
                }
            )

        # Compose Effective Assessment Baseline for this organisation
        eff_res = client.post(
            f"/v1/enterprise/baselines/{baseline_id}/effective-baseline",
            headers={"X-Tenant-ID": tenant_id, "X-Actor": "rev.1", "X-Role": "reviewer"},
            json={"as_of_date": "2026-11-02"},
        )
        assert eff_res.status_code == 201
        eff_data = eff_res.json()

        # Upload a custom-layout XLSX questionnaire for this organisation
        xlsx_bytes = _build_xlsx_bytes(
            sheet_name="Governance_Controls" if "bank" in org_id else "Assurance_Questions",
            headers=["Question ID", "Question", "Risk Domain", "Response (with Qualifying Statement)"],
            rows=[
                [
                    "Q-ORG-01",
                    "Has an accountable privacy owner been assigned and is a current privacy policy maintained for the AI system?",
                    "Privacy & Data Governance",
                    "Yes",
                ],
                [
                    "Q-ORG-02",
                    "Do all automated customer refunds above AUD 500 require pre-execution Authorised Officer human approval before payment execution?",
                    "Human Oversight",
                    "Yes",
                ],
                [
                    "Q-ORG-03",
                    "Are all prompts and model outputs recorded via prompt logging in the audit telemetry log?",
                    "Audit & Telemetry",
                    "Yes",
                ],
            ],
        )
        q_res = client.post(
            "/v1/questionnaires/import",
            headers={"X-Tenant-ID": tenant_id, "X-Actor": "analyst.1", "X-Role": "analyst"},
            json={
                "filename": f"{org_id}_questionnaire.xlsx",
                "workbook_base64": base64.b64encode(xlsx_bytes).decode("ascii"),
            },
        )
        assert q_res.status_code == 200
        q_id = q_res.json()["metadata"]["questionnaire_id"]

        # Run CoverageAssessment explicitly bound to the EffectiveAssessmentBaseline
        cov_res = client.post(
            "/v1/assessments/coverage",
            headers={"X-Tenant-ID": tenant_id, "X-Actor": "analyst.1", "X-Role": "analyst"},
            json={
                "questionnaire_id": q_id,
                "assessment_mode": "enterprise_enhanced",
                "enterprise_baseline_id": baseline_id,
                "effective_baseline_id": eff_data["effective_baseline_id"],
                "effective_baseline_sha256": eff_data["effective_baseline_sha256"],
                "as_of_date": "2026-11-02",
            },
        )
        assert cov_res.status_code == 201
        cov_body = cov_res.json()
        assert cov_body["assessment_basis"] == "effective_assessment_baseline"
        assert cov_body["effective_baseline_binding_mode"] == "explicit_validated_effective_baseline"
        assert cov_body["effective_baseline_id"] == eff_data["effective_baseline_id"]
        # Without human-approved question-to-obligation-facet mappings, confirmed regulatory coverage MUST be 0
        if cov_body["metrics"]["confirmed_covered"] > 0:
            false_confirmed_coverage_count += cov_body["metrics"]["confirmed_covered"]

    # Compute macro Precision, Recall, F1 across classes present in y_true
    labels = sorted(set(y_true))
    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []
    for lbl in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lbl and p == lbl)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lbl and p == lbl)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lbl and p != lbl)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    overall_acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    return {
        "split": split_name,
        "sample_size": total_expected_clauses,
        "retrieval_query_count": retrieval_queries,
        "document_extraction_accuracy": round(extracted_matched_count / total_expected_clauses, 4),
        "source_citation_accuracy": round(citation_traceable_count / total_expected_clauses, 4),
        "candidate_recall_at_1": round(recall_at_1_hits / max(retrieval_queries, 1), 4),
        "candidate_recall_at_5": round(recall_at_5_hits / max(retrieval_queries, 1), 4),
        "relationship_accuracy": round(overall_acc, 4),
        "macro_precision": round(sum(precisions) / len(precisions), 4),
        "macro_recall": round(sum(recalls) / len(recalls), 4),
        "macro_f1": round(sum(f1s) / len(f1s), 4),
        "false_equivalence_rate": round(false_equivalences / total_expected_clauses, 4),
        "false_conflict_rate": round(false_conflicts / total_expected_clauses, 4),
        "false_confirmed_coverage_rate": round(false_confirmed_coverage_count / total_expected_clauses, 4),
        "unresolved_surfacing_rate": round(
            expected_human_res_flagged / max(expected_human_res_total, 1), 4
        ),
        "cases": case_records,
    }


def test_e11_11_end_to_end_multi_org_dev_and_held_out_benchmark_pipeline(
    client, regulatory_pack
):
    """Execute the full end-to-end benchmark across Dev (18 clauses, 2 orgs) and
    Held-Out (18 clauses, 2 orgs) splits from raw PDF, DOCX, and TXT files through
    Effective Baseline composition and Questionnaire Coverage Assessment.
    """
    dev_clauses = [c for c in E11_BENCHMARK_CLAUSES if c.split == "dev"]
    ho_clauses = [c for c in E11_BENCHMARK_CLAUSES if c.split == "held_out"]
    assert len(dev_clauses) == 18
    assert len(ho_clauses) == 18

    dev_metrics = _evaluate_split_end_to_end("dev", dev_clauses, client, regulatory_pack)
    ho_metrics = _evaluate_split_end_to_end("held_out", ho_clauses, client, regulatory_pack)

    for m in (dev_metrics, ho_metrics):
        # Hard safety invariants: 0.0% False Equivalence and 0.0% False Confirmed Coverage
        assert m["false_equivalence_rate"] == 0.0, f"False equivalence in {m['split']}: {m}"
        assert m["false_confirmed_coverage_rate"] == 0.0
        assert m["false_conflict_rate"] == 0.0
        assert m["document_extraction_accuracy"] == 1.0
        assert m["source_citation_accuracy"] == 1.0
        assert m["candidate_recall_at_1"] >= 0.75
        assert m["candidate_recall_at_5"] >= 0.85
        assert m["relationship_accuracy"] >= 0.75
        assert m["unresolved_surfacing_rate"] >= 0.85
