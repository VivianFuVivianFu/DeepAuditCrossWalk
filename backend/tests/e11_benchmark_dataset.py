"""Shared E1.1 synthetic benchmark clauses and in-memory document builders."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from docx import Document

from banking_crosswalk.models import ReconciliationRelationship


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
