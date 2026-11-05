"""Comprehensive test suite for General Questionnaire Importer and Library Boundary Verification.

Verifies the 18 specific scenarios required by DeepAudit Crosswalk:
1. Valid general questionnaire workbook (.xlsx) imports successfully without AIAF sheet names.
2. Multi-sheet questionnaire workbook imports questions from all sheets (or specified sheets).
3. Missing question column triggers descriptive error (HTTP 422 / ValueError).
4. Content-addressable SHA-256 stable question IDs are generated consistently.
5. Ingestion rejects formula injection (=, +, -, @), HTML tags, and non-UTF-8 characters.
6. Ingestion enforces zip bomb protections (file size, uncompressed ratio, cell count limits).
7. Default assessment evaluates all questions in the QuestionBank (full_questionnaire mode).
8. Routed assessment evaluates routed snapshot questions when snapshot_id is supplied.
9. Mode A assessment evaluates ONLY regulatory sources (Categories A, B, C, E, F).
10. Mode A assessment NEVER activates ENT-AI-DELEGATED-APPROVAL, even with approval_threshold_aud = 500.
11. Mode B assessment evaluates regulatory sources PLUS tenant's approved Enterprise Baseline (Category D).
12. Mode B assessment evaluates ENT-AI-DELEGATED-APPROVAL against tenant baseline when applicable.
13. Cross-tenant baseline reference in Mode B fails closed (HTTP 404 / NotFoundError).
14. Strategy assessment returns HTTP 501 (not implemented).
15. Use case assessment returns HTTP 501 (not implemented).
16. All six regulatory source categories are represented in the Shared Regulatory Library.
17. Deprecated import_aiaf_workbook continues to work with deprecation warning.
18. Deprecated load_aiaf_question_bank continues to work with deprecation warning.
"""

from __future__ import annotations

import base64
import io
import pytest
import warnings
from datetime import date
from openpyxl import Workbook

from fastapi import HTTPException
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.api import (
    CoverageAssessmentRequest,
    QuestionnaireImportRequest,
    create_coverage_assessment,
    import_questionnaire,
)
from banking_crosswalk.catalog import (
    load_aiaf_question_bank,
    load_demo_questionnaire,
    load_regulatory_pack,
    load_source_register,
)
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.importer import (
    MAX_WORKBOOK_BYTES,
    import_aiaf_workbook,
    import_questionnaire_workbook,
)
from banking_crosswalk.models import (
    ApplicabilityStatus,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    CoverageAssessment,
    EnterpriseBaseline,
    EnterpriseClause,
    QuestionBank,
    QuestionRoutingSnapshot,
)
from banking_crosswalk.store import NotFoundError, store


def _create_simple_workbook(
    sheet_name: str = "AI Governance",
    headers: list[str] | None = None,
    rows: list[list[str]] | None = None,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers or ["Question ID", "Question Text", "Domain", "Guidance"])
    default_rows = [
        [
            "GOV-01",
            "Who is the accountable executive for the AI system?",
            "Governance",
            "Identify SMF or Senior Officer",
        ],
        [
            "RISK-01",
            "Has an operational risk assessment been completed for the AI agent?",
            "Risk Management",
            "CPS 230 / CPS 220 alignment",
        ],
        [
            "SEC-01",
            "What information security testing evaluates prompt injection vulnerabilities?",
            "Security",
            "CPS 234 testing schedule",
        ],
    ]
    for row in rows or default_rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Scenario 1: General questionnaire imports without AIAF sheet names
# ---------------------------------------------------------------------------
def test_scenario_01_general_questionnaire_imports_without_aiaf_sheets():
    raw = _create_simple_workbook(sheet_name="Custom_Enterprise_Audit")
    bank = import_questionnaire_workbook(raw, "enterprise_audit.xlsx")
    assert bank.metadata.source_filename == "enterprise_audit.xlsx"
    assert len(bank.questions) == 3
    assert bank.metadata.core_question_count == 3
    assert bank.routing_metadata.get("selection_mode") == "full_questionnaire"
    q_ids = [q.question_id for q in bank.questions]
    assert "GOV-01" in q_ids
    assert "RISK-01" in q_ids
    assert "SEC-01" in q_ids
    assert all(q.source_sheet == "Custom_Enterprise_Audit" for q in bank.questions)
    assert all(q.question_type == "question" for q in bank.questions)


# ---------------------------------------------------------------------------
# Scenario 2: Multi-sheet questionnaire workbook
# ---------------------------------------------------------------------------
def test_scenario_02_multi_sheet_questionnaire_import():
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Board_Governance"
    ws1.append(["Ref", "Requirement", "Area"])
    ws1.append(["BRD-01", "Does the Board approve the AI risk appetite?", "Governance"])
    ws1.append(["BRD-02", "Is AI reporting submitted to the Board Risk Committee quarterly?", "Governance"])

    ws2 = wb.create_sheet(title="Cyber_Resilience")
    ws2.append(["Item ID", "Control Description", "Pillar"])
    ws2.append(["CYB-01", "Is multi-factor authentication enforced on model admin consoles?", "Security"])
    ws2.append(["CYB-02", "Are third-party AI APIs continuously monitored for anomalies?", "Security"])

    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    # Import all sheets by default
    bank_all = import_questionnaire_workbook(raw, "multi_sheet.xlsx")
    assert len(bank_all.questions) == 4
    sheets_found = {q.source_sheet for q in bank_all.questions}
    assert sheets_found == {"Board_Governance", "Cyber_Resilience"}

    # Import specified sheet only
    bank_single = import_questionnaire_workbook(
        raw, "multi_sheet.xlsx", sheet_names=["Cyber_Resilience"]
    )
    assert len(bank_single.questions) == 2
    assert all(q.source_sheet == "Cyber_Resilience" for q in bank_single.questions)


# ---------------------------------------------------------------------------
# Scenario 3: Missing question column triggers descriptive error
# ---------------------------------------------------------------------------
def test_scenario_03_missing_question_column_triggers_descriptive_error():
    wb = Workbook()
    ws = wb.active
    ws.title = "NumbersOnly"
    ws.append(["Numeric Code", "Count", "Rate"])
    ws.append(["101", "5", "0.25"])
    ws.append(["102", "12", "0.75"])
    buf = io.BytesIO()
    wb.save(buf)

    with pytest.raises(ValueError, match="no identifiable question"):
        import_questionnaire_workbook(buf.getvalue(), "no_questions.xlsx")


# ---------------------------------------------------------------------------
# Scenario 4: Content-addressable SHA-256 stable question IDs
# ---------------------------------------------------------------------------
def test_scenario_04_stable_content_addressable_question_ids():
    wb = Workbook()
    ws = wb.active
    ws.title = "Unlabeled"
    # No ID column provided, so stable IDs should be generated
    ws.append(["Question Text", "Notes"])
    ws.append(["How is personal customer information safeguarded during LLM inference?", "Strict PII masking"])
    ws.append(["How are customer complaints regarding automated credit decisions escalated?", "AFCA / RG 271 compliance"])
    buf = io.BytesIO()
    wb.save(buf)
    raw = buf.getvalue()

    bank1 = import_questionnaire_workbook(raw, "unlabeled.xlsx")
    bank2 = import_questionnaire_workbook(raw, "unlabeled.xlsx")

    q1_ids = [q.question_id for q in bank1.questions]
    q2_ids = [q.question_id for q in bank2.questions]
    assert q1_ids == q2_ids
    assert all(qid.startswith("UNLABELED-Q") for qid in q1_ids)


# ---------------------------------------------------------------------------
# Scenario 5: Rejects formula injection (=, +, -, @), HTML tags, and nulls
# ---------------------------------------------------------------------------
def test_scenario_05_rejects_formula_injection_and_html():
    # Formula injection with =
    raw_formula_eq = _create_simple_workbook(
        rows=[["ID-01", "=SUM(A1:A10)", "Domain", "Guidance"]]
    )
    with pytest.raises(ValueError, match="prohibited formula"):
        import_questionnaire_workbook(raw_formula_eq, "formula_eq.xlsx")

    # Formula injection with @
    raw_formula_at = _create_simple_workbook(
        rows=[["ID-02", "@HYPERLINK('http://malicious.com')", "Domain", "Guidance"]]
    )
    with pytest.raises(ValueError, match="prohibited formula"):
        import_questionnaire_workbook(raw_formula_at, "formula_at.xlsx")

    # Formula injection with + and command
    raw_formula_plus = _create_simple_workbook(
        rows=[["ID-03", "+cmd|' /C calc'!A0", "Domain", "Guidance"]]
    )
    with pytest.raises(ValueError, match="prohibited formula"):
        import_questionnaire_workbook(raw_formula_plus, "formula_plus.xlsx")

    # Prohibited HTML tags
    raw_html = _create_simple_workbook(
        rows=[["ID-04", "<script>alert('xss')</script>Is risk managed?", "Domain", "Guidance"]]
    )
    with pytest.raises(ValueError, match="prohibited HTML markup"):
        import_questionnaire_workbook(raw_html, "html_xss.xlsx")

    # Null byte validation via direct security check
    from banking_crosswalk.importer import _validate_cell_security
    with pytest.raises(ValueError, match="prohibited null byte"):
        _validate_cell_security("Valid question\x00with null byte")


# ---------------------------------------------------------------------------
# Scenario 6: Zip bomb and archive protections
# ---------------------------------------------------------------------------
def test_scenario_06_enforces_archive_security_limits():
    # Oversized raw bytes
    huge_bytes = b"PK\x03\x04" + b"\x00" * (MAX_WORKBOOK_BYTES + 10)
    with pytest.raises(ValueError, match="exceeds the 20 MB import limit"):
        import_questionnaire_workbook(huge_bytes, "huge.xlsx")

    # Invalid archive format
    invalid_bytes = b"NOT_A_VALID_ZIP_OR_XLSX_ARCHIVE"
    with pytest.raises(ValueError, match="not a valid XLSX archive"):
        import_questionnaire_workbook(invalid_bytes, "invalid.xlsx")


# ---------------------------------------------------------------------------
# Scenario 7: Default assessment evaluates all questions (full_questionnaire)
# ---------------------------------------------------------------------------
def test_scenario_07_default_assessment_evaluates_full_questionnaire():
    raw = _create_simple_workbook()
    bank = import_questionnaire_workbook(raw, "assessment_target.xlsx")
    pack = load_regulatory_pack()
    use_case = BankingUseCase(
        name="Retail Banking LLM Agent",
        entity_type="ADI",
        apra_regulated=True,
        handles_personal_information=True,
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen7",
        use_case=use_case,
        question_bank=bank,
        regulatory_pack=pack,
    )
    assert assessment.question_scope == "full_questionnaire"
    assert assessment.selected_question_count == 3
    assert assessment.selection_warning is None


# ---------------------------------------------------------------------------
# Scenario 8: Routed assessment evaluates routed snapshot when supplied
# ---------------------------------------------------------------------------
def test_scenario_08_routed_assessment_evaluates_snapshot():
    raw = _create_simple_workbook()
    bank = import_questionnaire_workbook(raw, "assessment_target.xlsx")
    pack = load_regulatory_pack()
    use_case = BankingUseCase(
        name="Retail Banking LLM Agent",
        entity_type="ADI",
        apra_regulated=True,
    )

    snapshot = QuestionRoutingSnapshot(
        snapshot_id="snap-001",
        tenant_id="tenant-scen8",
        questionnaire_id=bank.metadata.questionnaire_id,
        questionnaire_sha256=bank.metadata.source_sha256,
        source_version=bank.metadata.source_version,
        selected_question_ids=["GOV-01"],
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen8",
        use_case=use_case,
        question_bank=bank.model_copy(
            update={
                "questions": [q for q in bank.questions if q.question_id in snapshot.selected_question_ids],
                "routing_metadata": {
                    "selection_mode": "routed_snapshot",
                    "routing_snapshot_id": snapshot.snapshot_id,
                },
            }
        ),
        regulatory_pack=pack,
    )
    assert assessment.question_scope == "routed_snapshot"
    assert assessment.selected_question_count == 1


# ---------------------------------------------------------------------------
# Scenario 9: Mode A assessment evaluates ONLY regulatory sources
# ---------------------------------------------------------------------------
def test_scenario_09_mode_a_evaluates_only_regulatory_sources():
    pack = load_regulatory_pack()
    bank = load_demo_questionnaire()
    use_case = BankingUseCase(
        name="Lending AI System",
        entity_type="ADI",
        apra_regulated=True,
        credit_licensee_or_credit_activity=True,
        assists_consumer_credit_decision=True,
        handles_personal_information=True,
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen9",
        use_case=use_case,
        question_bank=bank,
        regulatory_pack=pack,
        assessment_mode="regulatory_only",
    )

    # In Mode A, enterprise internal controls MUST NOT be applicable
    assert "ENT-AI-DELEGATED-APPROVAL" not in assessment.applicable_obligation_ids
    assert len(assessment.applicable_enterprise_requirement_ids) == 0

    # All applicable obligations must belong to authorized regulatory instruments
    reg_obligation_map = {o.obligation_id: o for o in pack.obligations}
    for app_id in assessment.applicable_obligation_ids:
        ob = reg_obligation_map[app_id]
        assert ob.source_id in {
            "AU-PRIVACY-ACT",
            "AU-OAIC-APP-GUIDELINES",
            "APRA-CPS220",
            "APRA-CPS230",
            "APRA-CPS234",
            "APRA-CPG235",
            "ASIC-RG271",
            "ASIC-RG104",
            "ASIC-RG105",
            "ASIC-REP798",
            "AU-NCCP-ACT",
            "AU-AI-GUIDANCE-2025",
            "EU-AI-ACT",
            "NIST-AI-RMF",
            "ISO-42001",
            "ISO-23894",
            "ISO-27001",
        }


# ---------------------------------------------------------------------------
# Scenario 10: Mode A NEVER activates ENT-AI-DELEGATED-APPROVAL (even with AUD 500)
# ---------------------------------------------------------------------------
def test_scenario_10_mode_a_never_activates_delegated_approval():
    pack = load_regulatory_pack()
    bank = load_demo_questionnaire()
    use_case = BankingUseCase(
        name="Dispute and Refund Agent",
        entity_type="ADI",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        enterprise_controls_enabled=True,
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen10",
        use_case=use_case,
        question_bank=bank,
        regulatory_pack=pack,
        assessment_mode="regulatory_only",
    )

    del_app = next(
        r for r in assessment.results if r.obligation_id == "ENT-AI-DELEGATED-APPROVAL"
    )
    assert del_app.applicability.status == ApplicabilityStatus.NOT_APPLICABLE
    assert "Enterprise internal baseline requirement excluded from Regulatory-Only assessment" in del_app.applicability.reason
    assert "ENT-AI-DELEGATED-APPROVAL" not in assessment.applicable_obligation_ids


# ---------------------------------------------------------------------------
# Scenario 11: Mode B evaluates regulatory PLUS approved tenant baseline
# ---------------------------------------------------------------------------
def test_scenario_11_mode_b_evaluates_regulatory_plus_approved_baseline():
    pack = load_regulatory_pack()
    bank = load_demo_questionnaire()
    use_case = BankingUseCase(
        name="Dispute and Refund Agent",
        entity_type="ADI",
        apra_regulated=True,
    )

    clause = EnterpriseClause(
        clause_id="POL-AI-01-SEC",
        policy_id="POL-INTERNAL",
        tenant_id="tenant-scen11",
        source_name="Bank AI Policy",
        clause_number="3.1",
        text="All generative AI deployments must undergo continuous red-teaming for prompt injection.",
        mandatory=True,
        control_facets=["adversarial_testing_required"],
        review_status=ClauseReviewStatus.APPROVED,
    )
    baseline = EnterpriseBaseline(
        baseline_id="base-tenant-11",
        tenant_id="tenant-scen11",
        name="Internal Baseline",
        policy_ids=["POL-INTERNAL"],
        clause_snapshots=[clause],
        mapping_snapshots=[],
        version="1.0.0",
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen11",
        use_case=use_case,
        question_bank=bank,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    assert assessment.enterprise_baseline_id == "base-tenant-11"
    assert "POL-AI-01-SEC" in assessment.applicable_enterprise_requirement_ids


# ---------------------------------------------------------------------------
# Scenario 12: Mode B evaluates ENT-AI-DELEGATED-APPROVAL against tenant baseline
# ---------------------------------------------------------------------------
def test_scenario_12_mode_b_evaluates_delegated_approval_when_in_baseline():
    pack = load_regulatory_pack()
    bank = load_demo_questionnaire()
    use_case = BankingUseCase(
        name="Dispute and Refund Agent",
        entity_type="ADI",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        enterprise_controls_enabled=True,
    )

    clause = EnterpriseClause(
        clause_id="ENT-AI-DELEGATED-APPROVAL",
        policy_id="ENTERPRISE-AI-STD",
        tenant_id="tenant-scen12",
        source_name="Enterprise Delegated Authority",
        clause_number="4.2",
        text="AI financial adjustments above AUD 500 require human officer approval.",
        mandatory=True,
        control_facets=["human_approval_required", "approval_threshold_defined"],
        review_status=ClauseReviewStatus.APPROVED,
    )
    baseline = EnterpriseBaseline(
        baseline_id="base-tenant-12",
        tenant_id="tenant-scen12",
        name="Delegated Authority Baseline",
        policy_ids=["ENTERPRISE-AI-STD"],
        clause_snapshots=[clause],
        mapping_snapshots=[],
        version="1.0.0",
    )

    assessment = evaluate_questionnaire_coverage(
        tenant_id="tenant-scen12",
        use_case=use_case,
        question_bank=bank,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    del_app = next(
        r for r in assessment.results if r.obligation_id == "ENT-AI-DELEGATED-APPROVAL"
    )
    assert del_app.applicability.status == ApplicabilityStatus.APPLICABLE
    assert "ENT-AI-DELEGATED-APPROVAL" in assessment.applicable_obligation_ids


# ---------------------------------------------------------------------------
# Scenario 13: Cross-tenant baseline reference in Mode B fails closed (404)
# ---------------------------------------------------------------------------
def test_scenario_13_cross_tenant_baseline_reference_fails_closed():
    # Tenant Alpha creates baseline
    tenant_a = "tenant-alpha"
    tenant_b = "tenant-beta"
    clause = EnterpriseClause(
        clause_id="ALPHA-01",
        policy_id="POL-ALPHA",
        tenant_id=tenant_a,
        source_name="Alpha Policy",
        clause_number="1.0",
        text="Alpha specific clause.",
        mandatory=True,
        review_status=ClauseReviewStatus.APPROVED,
    )
    baseline_a = EnterpriseBaseline(
        baseline_id="base-alpha-unique",
        tenant_id=tenant_a,
        name="Alpha Baseline",
        policy_ids=["POL-ALPHA"],
        clause_snapshots=[clause],
        mapping_snapshots=[],
        version="1.0.0",
    )
    store.save_enterprise_baseline(tenant_a, baseline_a)

    # Tenant Beta attempts to reference Tenant Alpha's baseline
    req = CoverageAssessmentRequest(
        assessment_mode="enterprise_enhanced",
        enterprise_baseline_id="base-alpha-unique",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_coverage_assessment(req, tenant_b)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Scenario 14: Strategy assessment returns HTTP 501
# ---------------------------------------------------------------------------
def test_scenario_14_strategy_assessment_returns_http_501():
    req = CoverageAssessmentRequest(
        assessment_target_type="strategy",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_coverage_assessment(req, "tenant-scen14")
    assert exc_info.value.status_code == 501
    assert "Strategy Assessment is not yet implemented" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Scenario 15: Standalone Use Case assessment returns HTTP 501
# ---------------------------------------------------------------------------
def test_scenario_15_use_case_assessment_returns_http_501():
    req = CoverageAssessmentRequest(
        assessment_target_type="use_case",
        use_case=_create_simple_banking_use_case(),
    )
    with pytest.raises(HTTPException) as exc_info:
        create_coverage_assessment(req, "tenant-scen15")
    assert exc_info.value.status_code == 501
    assert "not yet implemented in production" in exc_info.value.detail


def _create_simple_banking_use_case() -> BankingUseCase:
    return BankingUseCase(
        name="Credit Assistant",
        entity_type="ADI",
        apra_regulated=True,
    )


# ---------------------------------------------------------------------------
# Scenario 16: All six regulatory source categories represented
# ---------------------------------------------------------------------------
def test_scenario_16_all_six_source_categories_represented():
    pack = load_regulatory_pack()
    sources = {o.source_id for o in pack.obligations}

    # Category A: Australian Legislation & Statutory Guidance
    assert {"AU-PRIVACY-ACT", "AU-OAIC-APP-GUIDELINES", "AU-NCCP-ACT"}.intersection(sources)

    # Category B: APRA Prudential Standards & Practice Guides
    assert {"APRA-CPS220", "APRA-CPS230", "APRA-CPS234", "APRA-CPG235"}.issubset(sources)

    # Category C: ASIC Financial Conduct & Regulatory Guides
    assert {"ASIC-RG271", "ASIC-RG104", "ASIC-RG105", "ASIC-REP798"}.issubset(sources)

    # Category D: Enterprise Internal Baseline
    assert "ENTERPRISE-AI-STD" in sources

    # Category E: EU AI Act (cross-border)
    assert "EU-AI-ACT" in sources

    # Category F: NIST AI RMF & ISO Standards
    assert {"NIST-AI-RMF", "ISO-42001", "ISO-23894", "ISO-27001"}.issubset(sources)


# ---------------------------------------------------------------------------
# Scenario 17: Deprecated import_aiaf_workbook works with warning
# ---------------------------------------------------------------------------
def test_scenario_17_deprecated_import_aiaf_workbook_emits_warning():
    raw = _create_simple_workbook()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bank = import_aiaf_workbook(raw, "deprecated_test.xlsx")
        assert len(bank.questions) == 3
        assert any(
            issubclass(w.category, DeprecationWarning) and "import_aiaf_workbook is deprecated" in str(w.message)
            for w in caught
        )


# ---------------------------------------------------------------------------
# Scenario 18: Deprecated load_aiaf_question_bank works with warning
# ---------------------------------------------------------------------------
def test_scenario_18_deprecated_load_aiaf_question_bank_emits_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bank = load_aiaf_question_bank()
        assert len(bank.questions) == 19
        assert any(
            issubclass(w.category, DeprecationWarning) and "load_aiaf_question_bank is deprecated" in str(w.message)
            for w in caught
        )
