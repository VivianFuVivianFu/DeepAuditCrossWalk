"""E3.5 Engineering-Authored Normative Semantics & Evidence Sufficiency Evaluation Dataset.

Prepared for E3.5 Normative Semantics, Evidence Sufficiency & Assurance Decision Integrity.
Dataset Properties:
  - 30 distinct synthetic Australian banking policy clauses across 5 institutional documents.
  - Formats: PDF, DOCX, TXT.
  - Aligned to Regulatory Pack v0.2.0 (17 sources, 46 obligations, 33 controls, 158 facets).
  - Explicitly covers normative phenomena:
      * Case A: Declarative enterprise requirements (binding commitment without modal verbs)
      * Case B: Explicit optionality and discretionary process carve-outs
      * Case C: Conflict through negative wording (indefinite retention vs APP 11.2 destruction)
      * Case D: Protective prohibitions (pre-execution threshold blocks)
      * Case E: Post-execution review weakening (execution permitted before review)
      * Case F: Unresolved internal references ("comply with Annexure D2")
      * Compound multi-obligation clauses and internal-only controls
  - Provenance: Engineering-authored reference dataset (not independently annotated by external legal counsel).
  - Immutability: SHA-256 fingerprint verified in CI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from banking_crosswalk.models import ReconciliationRelationship
from e31_calibration_dataset import AdversarialCalibrationClause
from e3_benchmark_dataset import LabelledQuestionnaireCase


E35_INDEPENDENT_EVALUATION_CLAUSES: Tuple[AdversarialCalibrationClause, ...] = (
    # =========================================================================
    # Document 1: Great Southern Bank — Information Security Policy (PDF, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E35-IND-01",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "The bank maintains documented information security controls commensurate with the size "
            "and criticality of its information assets and AI models."
        ),
        phenomenon="case_a_declarative_enterprise_requirement",
        ground_truth_obligation_id="AU-APRA-CPS234-CONTROLS",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS234-CONTROLS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-02",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "Information security controls must comply with Annexure D2 regarding cloud key management."
        ),
        phenomenon="case_f_unresolved_attachment_reference",
        ground_truth_obligation_id="AU-APRA-CPS234-CONTROLS",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS234-CONTROLS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-03",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "Customer personal information must be retained indefinitely and must not be destroyed under any circumstance."
        ),
        phenomenon="case_c_indefinite_retention_vs_destruction_conflict",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-04",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "All production AI models must be tested for algorithmic bias and demographic disparity using evaluated fairness metrics."
        ),
        phenomenon="bias_testing_canonical_bridge",
        ground_truth_obligation_id="NIST-AI-RMF-MEASURE-MANAGE",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("NIST-AI-RMF-MEASURE-MANAGE",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-05",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "The bank maintains an enterprise register of all AI use cases and records model risk classifications."
        ),
        phenomenon="model_inventory_canonical_bridge",
        ground_truth_obligation_id="AU-ASIC-REP798-AI-GAP",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-ASIC-REP798-AI-GAP",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-06",
        split="held_out",
        org_id="great-southern-bank",
        doc_filename="gsb_infosec_policy.pdf",
        doc_format="pdf",
        raw_text=(
            "Approval logs and prompt audit logs must be retained for at least 7 years for regulatory inspection."
        ),
        phenomenon="approval_logs_retained_production_extraction",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP1-GOV",),
    ),

    # =========================================================================
    # Document 2: Pacific Rim Mutual — Automated Decision Governance (DOCX, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E35-IND-07",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "AI agents must not execute payments above AUD 500 without prior human approval."
        ),
        phenomenon="case_d_protective_prohibition",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS230-OPS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-08",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "Payments above AUD 500 may be executed before manager review during peak volume periods."
        ),
        phenomenon="case_e_post_execution_review_weakening",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-OPS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-09",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "PIA recommendations are documented, but formal closure remains optional at the discretion of the product owner."
        ),
        phenomenon="case_b_explicit_optionality",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP1-GOV",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-10",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "All outbound transfers exceeding AUD 10,000 require senior executive sign-off prior to release."
        ),
        phenomenon="stricter_financial_threshold",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS230-OPS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-11",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "The mutual does not require formal risk assessments for internal productivity AI tools."
        ),
        phenomenon="absence_of_control_direct_conflict",
        ground_truth_obligation_id="AU-APRA-CPS220-RMF",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS220-RMF",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-12",
        split="held_out",
        org_id="pacific-rim-mutual",
        doc_filename="prm_automated_decision_standard.docx",
        doc_format="docx",
        raw_text=(
            "Customer dispute escalations must be handled within 30 days unless an informal resolution is agreed."
        ),
        phenomenon="conditional_dispute_resolution",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT",),
    ),

    # =========================================================================
    # Document 3: Tasmanian Coastal Credit — Privacy & Vendor Policy (TXT, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E35-IND-13",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Tasmanian Coastal Credit ensures that customer personal data is destroyed or de-identified when no longer required."
        ),
        phenomenon="declarative_retention_compliance",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-14",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Cross-border disclosures must comply with Appendix 3 regarding approved offshore jurisdictions."
        ),
        phenomenon="unresolved_appendix_dependency",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP8-CROSSBORDER",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-15",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Material service providers delivering AI services must notify the bank of significant incidents within 24 hours."
        ),
        phenomenon="stricter_vendor_notification_timeframe",
        ground_truth_obligation_id="AU-APRA-CPS230-NOTIFY",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS230-NOTIFY",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-16",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Customer consent is obtained prior to collecting sensitive biometrics for fraud prevention."
        ),
        phenomenon="declarative_biometric_collection",
        ground_truth_obligation_id="AU-PRIV-APP3-COLLECT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP3-COLLECT",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-17",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Staff may optionally conduct vendor security questionnaires at their discretion for non-core vendors."
        ),
        phenomenon="optional_vendor_assessment",
        ground_truth_obligation_id="AU-APRA-CPS234-CONTROLS",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS234-CONTROLS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-18",
        split="held_out",
        org_id="tasmanian-coastal-credit",
        doc_filename="tcc_privacy_and_vendor_policy.txt",
        doc_format="txt",
        raw_text=(
            "Credit scoring AI algorithms must verify accuracy and explainability before automated denial decisions."
        ),
        phenomenon="credit_activity_fairness",
        ground_truth_obligation_id="AU-NCCP-S47-CONDUCT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NCCP-S47-CONDUCT",),
    ),

    # =========================================================================
    # Document 4: Southern Cross Institutional Bank — Operational Risk (PDF, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E35-IND-19",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "The Board Risk Committee conducts annual reviews of all enterprise AI risk management frameworks."
        ),
        phenomenon="board_oversight_declarative",
        ground_truth_obligation_id="AU-APRA-CPS220-RMF",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS220-RMF",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-20",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "AI operational disruption tolerance limits are defined per Schedule B4 of the Business Continuity Plan."
        ),
        phenomenon="unresolved_schedule_reference",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-OPS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-21",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "Critical business operations must maintain tested offline recovery procedures for all automated decision models."
        ),
        phenomenon="cps230_business_continuity",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-OPS",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-22",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "Under Article 26 of the EU AI Act, deployers of high-risk AI assign natural persons with necessary competence and authority to oversee AI system operation."
        ),
        phenomenon="eu_ai_act_deployer_oversight",
        ground_truth_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART26-27-DEPLOYER-CREDIT",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-23",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "High-risk AI automatically generated logs are retained for at least 6 months under Article 26(6)."
        ),
        phenomenon="eu_ai_act_log_retention",
        ground_truth_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART26-27-DEPLOYER-CREDIT",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-24",
        split="held_out",
        org_id="southern-cross-inst",
        doc_filename="scib_operational_risk_framework.pdf",
        doc_format="pdf",
        raw_text=(
            "The bank has not yet implemented real-time drift detection for consumer credit scoring."
        ),
        phenomenon="unimplemented_control_status",
        ground_truth_obligation_id="AU-NCCP-S47-CONDUCT",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NCCP-S47-CONDUCT",),
    ),

    # =========================================================================
    # Document 5: Frontier Digital Bank — AI Ethics & Architecture (TXT, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E35-IND-25",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Frontier Digital Bank ensures human intervention and kill-switch override capabilities for autonomous trading agents."
        ),
        phenomenon="human_oversight_and_kill_switch",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-26",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Synthetic audio and video generated for customer communication must be clearly marked and disclosed under Article 50."
        ),
        phenomenon="synthetic_content_disclosure",
        ground_truth_obligation_id="EU-AIA-ART50-TRANSPARENCY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART50-TRANSPARENCY",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-27",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Notifiable data breaches involving serious harm must be notified to the OAIC and affected individuals as soon as practicable."
        ),
        phenomenon="ndb_scheme_compliance",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-NDB-S26WE",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-28",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Eligible data breaches may be resolved internally without OAIC notification if management determines customer impact is minor."
        ),
        phenomenon="ndb_unauthorized_exemption_conflict",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-NDB-S26WE",),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-29",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Branch staff cafeteria menus and social club events are managed through the staff intranet portal."
        ),
        phenomenon="corporate_noise_unmapped",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E35-IND-30",
        split="held_out",
        org_id="frontier-digital-bank",
        doc_filename="fdb_ai_ethics_architecture.txt",
        doc_format="txt",
        raw_text=(
            "Building maintenance and office cleaning operations are scheduled on Saturday evenings."
        ),
        phenomenon="facilities_noise_unmapped",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
)


E35_INDEPENDENT_QUESTIONNAIRE_CASES: Tuple[LabelledQuestionnaireCase, ...] = (
    LabelledQuestionnaireCase(
        case_id="E35-Q-01",
        split="held_out",
        question_id="Q-E35-CPS234-CONTROLS",
        domain="security",
        prompt="Does the bank maintain documented information security controls commensurate with information asset and AI model criticality under CPS 234?",
        response="Documented infosec policies and technical controls commensurate with size and asset risk.",
        ground_truth_obligation_id="AU-APRA-CPS234-CONTROLS",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-02",
        split="held_out",
        question_id="Q-E35-APP11-RETENTION",
        domain="privacy",
        prompt="Are customer personal records destroyed or de-identified when retention schedules expire under APP 11.2?",
        response="Automated data purging and de-identification pipelines enforce retention expiration.",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-03",
        split="held_out",
        question_id="Q-E35-CPS230-OPS",
        domain="financial_delegation",
        prompt="Does the bank require pre-execution human approval for automated payments above AUD 500 under operational risk standards?",
        response="Automated threshold intercept blocks execution until explicit supervisor approval.",
        ground_truth_obligation_id="AU-APRA-CPS230-OPS",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-04",
        split="held_out",
        question_id="Q-E35-APP1-GOV",
        domain="governance",
        prompt="Are approval audit logs retained to ensure complete traceability of human sign-offs and model governance under APP 1?",
        response="Append-only audit logs capture human approver identity, timestamps, and model rationale.",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-05",
        split="held_out",
        question_id="Q-E35-NIST-AI-RMF",
        domain="fairness",
        prompt="Are algorithmic bias and fairness metrics evaluated across credit scoring AI models under NIST AI RMF MEASURE?",
        response="Disparate impact ratio, demographic parity, and equal opportunity metrics evaluated before deployment.",
        ground_truth_obligation_id="NIST-AI-RMF-MEASURE-MANAGE",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-06",
        split="held_out",
        question_id="Q-E35-ASIC-REP798",
        domain="accountability",
        prompt="Is an enterprise AI use case register maintained for all active models and risk classifications under ASIC REP 798?",
        response="Central model inventory categorises all AI models by criticality and consumer impact.",
        ground_truth_obligation_id="AU-ASIC-REP798-AI-GAP",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-07",
        split="held_out",
        question_id="Q-E35-NAIC-AI6",
        domain="human_oversight",
        prompt="Are human oversight and kill-switch capabilities implemented for high-risk autonomous AI workflows under Principle 6?",
        response="Operations control desk maintains emergency kill switches and manual intervention controls.",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
    ),
    LabelledQuestionnaireCase(
        case_id="E35-Q-08",
        split="held_out",
        question_id="Q-E35-NDB",
        domain="privacy_breach",
        prompt="Does the bank notify the OAIC and individuals of eligible data breaches involving serious harm under Part IIIC?",
        response="Mandatory NDB breach assessment procedure escalates eligible breaches to OAIC and customers.",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
    ),
)


def serialize_e35_dataset_payload() -> dict:
    clauses_payload = [
        {
            "case_id": c.case_id,
            "split": c.split,
            "org_id": c.org_id,
            "doc_filename": c.doc_filename,
            "doc_format": c.doc_format,
            "raw_text": c.raw_text,
            "phenomenon": c.phenomenon,
            "ground_truth_obligation_id": c.ground_truth_obligation_id,
            "ground_truth_relationship": c.ground_truth_relationship.value,
            "expects_human_resolution": c.expects_human_resolution,
            "expected_obligation_ids": list(c.expected_obligation_ids),
        }
        for c in E35_INDEPENDENT_EVALUATION_CLAUSES
    ]
    q_payload = [
        {
            "case_id": q.case_id,
            "split": q.split,
            "question_id": q.question_id,
            "domain": q.domain,
            "prompt": q.prompt,
            "response": q.response,
            "ground_truth_obligation_id": q.ground_truth_obligation_id,
        }
        for q in E35_INDEPENDENT_QUESTIONNAIRE_CASES
    ]
    return {
        "dataset_id": "DEEPAUDIT-E35-INDEPENDENT-EVAL-V1",
        "dataset_version": "1.0.0",
        "target_regulatory_pack_id": "AU-BANKING-REG-PACK-0.1",
        "target_regulatory_pack_version": "0.2.0",
        "n_clauses": len(clauses_payload),
        "n_questionnaire_cases": len(q_payload),
        "clauses": clauses_payload,
        "questionnaire_cases": q_payload,
    }


def compute_e35_dataset_sha256() -> str:
    """Compute deterministic SHA-256 fingerprint of the E3.5 independent dataset."""
    payload = serialize_e35_dataset_payload()
    canonical_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
