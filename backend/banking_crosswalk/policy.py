"""Enterprise policy extraction and two-way gap analysis.

Policy text is always treated as untrusted data.  Extraction is deterministic;
the parser records prompt-injection-like phrases instead of following them.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .applicability import decide_applicability
from .models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingRelationship,
    utc_now,
    ApplicabilityStatus,
    AtomicObligation,
    Authority,
    BankingUseCase,
    GapRecord,
    GapType,
    PolicyClause,
    PolicyGapAssessment,
    PolicyPack,
    QuestionBank,
    RegulatoryPack,
    authority_layer_bucket,
)


INJECTION_PATTERNS = [
    r"ignore (?:all|any|the) previous instructions?",
    r"system prompt",
    r"developer message",
    r"execute (?:this|the following) command",
    r"exfiltrat(?:e|ion)",
    r"bypass (?:security|policy|controls?)",
]

MANDATORY_PATTERN = re.compile(
    r"(?<!does not\s)(?<!do not\s)(?<!not\s)(?<!no\s)\b(must|shall|required to|is required|are required|requires?|may not|must not|is prohibited|are prohibited|will not|mandatory)\b",
    re.IGNORECASE,
)
NEGATION_OR_EXEMPTION_PATTERN = re.compile(
    r"\b(does not require|do not require|not required|no requirement for|no requirement to|is exempt|are exempt|exemption|must not be used)\b",
    re.IGNORECASE,
)
ABSENCE_OF_CONTROL_PATTERN = re.compile(
    r"\b(does not require|do not require|not required|no requirement for|no requirement to|never required|is not required|are not required)\b",
    re.IGNORECASE,
)
MERE_TOPIC_REFERENCE_PATTERN = re.compile(
    r"\b(is considering|are considering|considering introducing|considering adopting|exploring(?: the)?|evaluating the introduction of|discussions are underway|plans to explore|may consider)\b",
    re.IGNORECASE,
)
PROHIBITION_BLOCK_PATTERN = re.compile(
    r"\b(must not execute|shall not execute|cannot proceed|prohibited prior to|prior to (?:payment|execution|transaction release)|before (?:payment|execution)|bypassing .* is prohibited|under no circumstances shall .* be bypassed|without .* is prohibited)\b",
    re.IGNORECASE,
)
STAFF_PROHIBITION_PATTERN = re.compile(
    r"\b(staff are prohibited from|employees are prohibited from|prohibited from conducting|prohibited from using)\b",
    re.IGNORECASE,
)
EXEMPTION_PATTERN = re.compile(
    r"\b(is exempt|are exempt|exemption for|exempt from)\b",
    re.IGNORECASE,
)
UNIMPLEMENTED_PATTERN = re.compile(
    r"\b(not yet implemented|has not yet been implemented|have not yet been implemented|workflow has not been (?:built|deployed)|not currently operational|not currently implemented|pending implementation)\b",
    re.IGNORECASE,
)
CONDITIONAL_PATTERN = re.compile(
    r"\b(unless an authorised exception applies|unless approved|except where|subject to prior approval of an exception|in the event of|provided that)\b",
    re.IGNORECASE,
)
CURRENCY_PATTERN = re.compile(
    r"\b(AUD|USD|EUR|GBP)\b",
    re.IGNORECASE,
)
THRESHOLD_AMOUNT_PATTERN = re.compile(
    r"(?:(?:AUD|USD|EUR|GBP)\s*\$?\s*|\$\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d,])",
    re.IGNORECASE,
)
AUD_PATTERN = THRESHOLD_AMOUNT_PATTERN


def _detect_threshold_operator(clause_text: str) -> Optional[str]:
    lower = clause_text.lower()
    if re.search(r"\b(at or above|at least|greater than or equal to|>=)\b", lower):
        return ">="
    if re.search(r"\b(exceeding|above|greater than|over|>)\b", lower):
        return ">"
    if re.search(r"\b(up to and including|at most|less than or equal to|<=)\b", lower):
        return "<="
    if re.search(r"\b(below|less than|<)\b", lower):
        return "<"
    return None


def _detect_threshold_currency(clause_text: str) -> Optional[str]:
    match = CURRENCY_PATTERN.search(clause_text)
    if match:
        return match.group(1).upper()
    if "$" in clause_text:
        return "AUD"
    return None


def _detect_approval_timing(clause_text: str) -> Optional[str]:
    lower = clause_text.lower()
    if any(
        p in lower
        for p in (
            "before payment",
            "before execution",
            "prior to payment",
            "prior to execution",
            "prior to transaction release",
            "prior to",
            "must not execute",
            "shall not execute",
            "cannot proceed",
            "prohibited prior to",
            "pre-execution",
            "pre execution",
        )
    ):
        return "pre_execution"
    if any(
        p in lower
        for p in (
            "after payment",
            "after execution",
            "post-execution",
            "post execution",
            "retrospective",
            "audit review after",
            "subsequent review",
        )
    ):
        return "post_execution"
    return None


def _detect_approval_role(clause_text: str) -> Optional[str]:
    lower = clause_text.lower()
    if "senior manager" in lower:
        return "Senior Manager"
    if "authorised officer" in lower or "authorized officer" in lower:
        return "Authorised Officer"
    if "risk lead" in lower:
        return "Risk Lead"
    if "head of" in lower:
        return "Head of Department"
    if "two-up manager" in lower or "dual sign-off" in lower or "four-eyes" in lower:
        return "Two-Up / Dual Sign-off"
    return None


def _detect_conditions(clause_text: str) -> Tuple[bool, Optional[str]]:
    m = re.search(
        r"\b(in the event of [^,.;]+|provided that [^,.;]+|where [^,.;]+)\b",
        clause_text,
        re.IGNORECASE,
    )
    if m:
        return True, m.group(0).strip()
    return False, None


def _detect_exceptions(clause_text: str) -> Tuple[bool, Optional[str]]:
    m = re.search(
        r"\b(unless [^,.;]+|except where [^,.;]+|exempt for [^,.;]+|exempt from [^,.;]+)\b",
        clause_text,
        re.IGNORECASE,
    )
    if m:
        return True, m.group(0).strip()
    return False, None


def _detect_implementation_status(clause_text: str) -> Optional[str]:
    if UNIMPLEMENTED_PATTERN.search(clause_text):
        return "unimplemented"
    return None


GENERIC_FACET_PATTERNS: Dict[str, Sequence[str]] = {
    "human_approval_required": (
        "human approval",
        "manual approval",
        "approved by a human",
        "authorised officer",
    ),
    "approval_threshold_defined": ("above aud", "over aud", "aud $", "$"),
    "pre_execution_block": (
        "before payment",
        "before execution",
        "must not execute",
        "prevent execution",
        "cannot proceed",
    ),
    "approval_logs_retained": (
        "approval log",
        "audit log",
        "record approval",
        "retain approval",
        "approval record",
    ),
    "privacy_governance": (
        "privacy",
        "personal information",
        "consent",
        "collection notice",
    ),
    "information_security": (
        "information security",
        "cyber",
        "access control",
        "vulnerability",
        "security testing",
    ),
    "complaint_handling": ("complaint", "dissatisfaction", "idr", "afca"),
    "service_provider_management": (
        "vendor",
        "service provider",
        "third party",
        "supplier",
        "contract",
    ),
    "risk_management": (
        "risk assessment",
        "risk owner",
        "risk register",
        "risk management",
    ),
    "business_continuity": (
        "business continuity",
        "fallback",
        "recovery",
        "critical operation",
    ),
    "monitoring_and_review": (
        "monitor",
        "review",
        "test results",
        "control effectiveness",
    ),
}


QUESTION_KEYWORDS: Dict[str, Sequence[str]] = {
    "human_approval_required": (
        "human approval",
        "manual approval",
        "approved by a human",
        "authorised officer approval",
        "authorized officer approval",
        "human sign-off",
        "dual sign-off",
        "manager sign-off",
        "manager approval",
    ),
    "approval_threshold_defined": ("threshold", "aud", "$500", "500"),
    "pre_execution_block": (
        "before execution",
        "before payment",
        "prior to execution",
        "prior to payment",
        "prevent execution",
        "cannot proceed",
        "pre-execution block",
    ),
    "approval_logs_retained": ("approval log", "audit log", "recorded", "traceability"),
    "privacy_governance": ("privacy", "personal information", "consent"),
    "information_security": ("information security", "cyber", "security controls"),
    "complaint_handling": ("complaint", "dissatisfaction", "contest"),
    "service_provider_management": ("vendor", "third party", "supplier"),
    "risk_management": ("risk assessment", "risk owner", "risk register"),
    "business_continuity": ("business continuity", "fallback", "recovery"),
    "monitoring_and_review": ("monitor", "review", "test"),
}


def _stable_clause_id(source_name: str, text: str) -> str:
    key = f"{source_name}|{' '.join(text.lower().split())}"
    return f"POL-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12].upper()}"


def _split_clauses(text: str) -> List[str]:
    # Preserve policy bullets/headings where possible, then split unusually
    # long lines into sentences.  Short descriptive fragments without a
    # normative verb are retained for traceability but marked non-mandatory.
    raw_lines = [
        re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[-*•])\s*", "", line).strip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    clauses: List[str] = []
    for line in raw_lines:
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", line) if len(line) > 320 else [line]
        clauses.extend(part.strip() for part in parts if part.strip())
    return clauses


def extract_policy_pack(
    *, tenant_id: str, name: str, text: str, version: str = "unversioned"
) -> PolicyPack:
    if len(text.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("Policy text exceeds the 10 MB import limit")
    warnings: List[str] = []
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            warnings.append(
                "Potential embedded instruction detected and treated as inert policy text: "
                + pattern
            )

    clauses: List[PolicyClause] = []
    for raw_clause in _split_clauses(text):
        clause_lower = raw_clause.lower()

        # Deterministic Category A: Absence of required control
        if ABSENCE_OF_CONTROL_PATTERN.search(raw_clause):
            clauses.append(
                PolicyClause(
                    clause_id=_stable_clause_id(name, raw_clause),
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    control_facets=[],
                    thresholds_aud=[],
                )
            )
            continue

        # Deterministic Category E: Policy exemption without active requirement
        if EXEMPTION_PATTERN.search(raw_clause) and not any(
            p in clause_lower for p in ("threshold", "require", "mandatory", "must")
        ):
            has_exc, _ = _detect_exceptions(raw_clause)
            clauses.append(
                PolicyClause(
                    clause_id=_stable_clause_id(name, raw_clause),
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    control_facets=[],
                    thresholds_aud=[],
                    has_exception_clause=has_exc,
                )
            )
            continue

        # Deterministic Category F: Mere topic reference
        is_topic = bool(MERE_TOPIC_REFERENCE_PATTERN.search(raw_clause))
        has_mandatory_words = any(
            w in clause_lower
            for w in ("must", "shall", "is required", "are required", "mandatory")
        )
        if is_topic and not has_mandatory_words:
            clauses.append(
                PolicyClause(
                    clause_id=_stable_clause_id(name, raw_clause),
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    control_facets=[],
                    thresholds_aud=[],
                )
            )
            continue

        facets = [
            facet
            for facet, phrases in GENERIC_FACET_PATTERNS.items()
            if any(phrase in clause_lower for phrase in phrases)
        ]
        thresholds = [
            float(match.replace(",", "")) for match in AUD_PATTERN.findall(raw_clause)
        ]
        if thresholds and "approval_threshold_defined" not in facets:
            facets.append("approval_threshold_defined")

        is_prohib_block = bool(PROHIBITION_BLOCK_PATTERN.search(raw_clause))
        if ("human_approval_required" in facets or is_prohib_block) and any(
            phrase in clause_lower
            for phrase in (
                "before payment",
                "before execution",
                "prior to payment",
                "prior to execution",
                "prior to",
                "must not execute",
                "cannot proceed",
                "prohibited prior to",
            )
        ):
            if "pre_execution_block" not in facets:
                facets.append("pre_execution_block")
            if "human_approval_required" not in facets and any(
                p in clause_lower for p in ("approval", "sign-off", "officer", "authoris")
            ):
                facets.append("human_approval_required")

        is_mand = bool(MANDATORY_PATTERN.search(raw_clause)) or is_prohib_block
        is_cond, _ = _detect_conditions(raw_clause)
        has_exc, _ = _detect_exceptions(raw_clause)

        clauses.append(
            PolicyClause(
                clause_id=_stable_clause_id(name, raw_clause),
                source_name=name,
                text=raw_clause,
                mandatory=is_mand,
                control_facets=facets,
                thresholds_aud=thresholds,
                threshold_operator=_detect_threshold_operator(raw_clause),
                threshold_currency=_detect_threshold_currency(raw_clause),
                approval_timing=_detect_approval_timing(raw_clause),
                required_approval_role=_detect_approval_role(raw_clause),
                is_conditional=is_cond,
                has_exception_clause=has_exc,
                implementation_status=_detect_implementation_status(raw_clause),
            )
        )

    if not clauses:
        warnings.append("No policy clauses were extracted from the supplied text.")
    if not any(clause.mandatory for clause in clauses):
        warnings.append(
            "No mandatory policy language (for example, must/shall/required) was detected."
        )

    return PolicyPack(
        policy_pack_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        version=version,
        clauses=clauses,
        warnings=warnings,
    )


def _obligation_facet_covered(
    facet: str, obligation: AtomicObligation, clauses: Sequence[PolicyClause]
) -> bool:
    phrases = [phrase.lower() for phrase in obligation.facet_keywords.get(facet, [])]
    facet_tokens = {token for token in facet.lower().split("_") if len(token) > 3}
    for clause in clauses:
        text = clause.text.lower()
        if any(phrase in text for phrase in phrases):
            return True
        clause_tokens = set(re.findall(r"[a-z]+", text))
        if facet_tokens and len(facet_tokens & clause_tokens) >= min(
            2, len(facet_tokens)
        ):
            return True
    return False


def _questionnaire_covers_generic_facet(
    facet: str, bank: QuestionBank, clause: PolicyClause
) -> bool:
    if facet == "approval_threshold_defined":
        # A generic question about thresholds is not enough: the questionnaire
        # must test the enterprise policy's exact numeric boundary.
        required_amounts = set(clause.thresholds_aud)
        if not required_amounts:
            return False
        assessed_amounts = {
            float(match.replace(",", ""))
            for question in bank.questions
            if not ABSENCE_OF_CONTROL_PATTERN.search(question.question_text)
            and any(
                term in question.question_text.lower()
                for term in ("approval", "refund", "payment", "sign-off", "transaction", "credit")
            )
            for match in AUD_PATTERN.findall(question.question_text)
        }
        return required_amounts.issubset(assessed_amounts)
    keywords = QUESTION_KEYWORDS.get(facet, (facet.replace("_", " "),))
    for question in bank.questions:
        if ABSENCE_OF_CONTROL_PATTERN.search(question.question_text):
            continue
        if facet == "pre_execution_block" and _detect_approval_timing(question.question_text) == "post_execution":
            continue
        lower = question.question_text.lower()
        if any(keyword in lower for keyword in keywords):
            return True
    return False


def _severity(obligation: AtomicObligation) -> str:
    if obligation.authority in {Authority.BINDING, Authority.ENFORCEABLE_GUIDANCE}:
        return "high"
    if obligation.authority is Authority.ENTERPRISE:
        return "medium"
    return "low"


def assess_policy_gaps(
    *,
    tenant_id: str,
    use_case: Optional[BankingUseCase] = None,
    policy_pack: PolicyPack,
    question_bank: QuestionBank,
    regulatory_pack: RegulatoryPack,
) -> PolicyGapAssessment:
    if use_case is None:
        use_case = BankingUseCase.enterprise_baseline()
    policy_gaps: List[GapRecord] = []
    questionnaire_gaps: List[GapRecord] = []
    conflicts: List[GapRecord] = []
    evidence_gaps: List[GapRecord] = []
    gaps_by_layer: Dict[str, List[GapRecord]] = {
        "binding_regulatory": [],
        "regulatory_guidance": [],
        "voluntary_frameworks": [],
        "enterprise_internal_controls": [],
    }

    mandatory_clauses = [clause for clause in policy_pack.clauses if clause.mandatory]
    for obligation in regulatory_pack.obligations:
        applicability = decide_applicability(obligation, use_case)
        if applicability.status is not ApplicabilityStatus.APPLICABLE:
            continue
        missing = [
            facet
            for facet in obligation.coverage_facets
            if not _obligation_facet_covered(facet, obligation, mandatory_clauses)
        ]
        if missing:
            gap = GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.ENTERPRISE_POLICY,
                title=f"Enterprise policy does not fully address {obligation.title}",
                severity=_severity(obligation),
                obligation_id=obligation.obligation_id,
                missing_facets=missing,
                recommendation=(
                    "Legal/Compliance and the policy owner should confirm applicability, then add mandatory "
                    "policy requirements for the missing facets."
                ),
                evidence_required=obligation.evidence_requirements,
            )
            bucket = authority_layer_bucket(obligation.authority)
            gaps_by_layer[bucket].append(gap)
            if obligation.authority in {
                Authority.BINDING,
                Authority.ENFORCEABLE_GUIDANCE,
            }:
                policy_gaps.append(gap)

    for clause in mandatory_clauses:
        missing = [
            facet
            for facet in clause.control_facets
            if not _questionnaire_covers_generic_facet(facet, question_bank, clause)
        ]
        if missing:
            questionnaire_gaps.append(
                GapRecord(
                    gap_id=str(uuid.uuid4()),
                    gap_type=GapType.QUESTIONNAIRE,
                    title="Questionnaire does not test a mandatory enterprise-policy control",
                    severity="high"
                    if any(
                        "approval" in facet or "execution" in facet for facet in missing
                    )
                    else "medium",
                    policy_clause_id=clause.clause_id,
                    missing_facets=missing,
                    recommendation=(
                        "Add a banking-overlay question or evidence requirement that tests the exact policy condition, "
                        "including numeric thresholds and non-bypass behaviour."
                    ),
                    evidence_required=[
                        "Approved policy clause",
                        "Question-to-policy mapping review",
                    ],
                )
            )

        evidence_gaps.append(
            GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.IMPLEMENTATION_EVIDENCE,
                title="Mandatory policy control has not been implementation-tested",
                severity="medium",
                policy_clause_id=clause.clause_id,
                missing_facets=list(clause.control_facets),
                recommendation="Connect the control to DeepAudit evidence review or behavioural testing and record a reviewer conclusion.",
                evidence_required=[
                    "System configuration",
                    "Execution trace",
                    "Control test result",
                ],
            )
        )

    observed_thresholds = sorted(
        {
            threshold
            for clause in mandatory_clauses
            for threshold in clause.thresholds_aud
        }
    )
    if len(observed_thresholds) > 1:
        conflicts.append(
            GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.CONTROL_CONFLICT,
                title="Enterprise policies contain conflicting AUD approval thresholds",
                severity="high",
                missing_facets=["single_authoritative_threshold"],
                recommendation=f"Policy owners must reconcile the observed thresholds: {observed_thresholds}.",
                evidence_required=["Approved delegated-authority schedule"],
            )
        )
    elif observed_thresholds and use_case.approval_threshold_aud is not None:
        policy_threshold = observed_thresholds[0]
        if policy_threshold != use_case.approval_threshold_aud:
            conflicts.append(
                GapRecord(
                    gap_id=str(uuid.uuid4()),
                    gap_type=GapType.CONTROL_CONFLICT,
                    title="Configured approval threshold conflicts with enterprise policy",
                    severity="critical",
                    missing_facets=["approval_threshold_aligned"],
                    recommendation=(
                        f"Align the system threshold AUD {use_case.approval_threshold_aud:g} to the approved policy "
                        f"threshold AUD {policy_threshold:g}, or obtain an authorised policy exception."
                    ),
                    evidence_required=[
                        "Delegated-authority policy",
                        "Production configuration",
                        "Exception approval",
                    ],
                )
            )

    return PolicyGapAssessment(
        assessment_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        policy_pack_id=policy_pack.policy_pack_id,
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        routing_snapshot_id=question_bank.routing_metadata.get("routing_snapshot_id"),
        selected_question_ids=[item.question_id for item in question_bank.questions],
        policy_gaps=policy_gaps,
        questionnaire_gaps=questionnaire_gaps,
        control_conflicts=conflicts,
        implementation_evidence_gaps=evidence_gaps,
        gaps_by_authority_layer=gaps_by_layer,
        policy_clauses=policy_pack.clauses,
        warnings=policy_pack.warnings,
    )



# ─────────────────────────────────────────────────────────────────────────────
# Enterprise Regulatory & Policy Layer: Extraction, Mapping & Multi-Doc Gaps
# ─────────────────────────────────────────────────────────────────────────────

ENTERPRISE_FACET_PATTERNS: Dict[str, Sequence[str]] = {
    "human_approval_required": (
        "human approval",
        "manual approval",
        "approved by a human",
        "authorised officer",
        "authorized officer",
        "senior manager approval",
        "manager approval",
        "supervisor approval",
        "sign-off",
        "dual sign-off",
        "dual approval",
    ),
    "approval_threshold_defined": (
        "above aud",
        "over aud",
        "aud $",
        "$",
        "threshold",
        "delegated authority",
    ),
    "pre_execution_block": (
        "before payment",
        "before execution",
        "prior to payment",
        "must not execute",
        "prohibited prior to",
    ),
    "zero_data_retention": (
        "zero data retention",
        "no data retention",
        "do not retain",
        "not retain customer data",
        "zdr",
        "zero-retention",
    ),
    "prompt_logging": (
        "prompt logging",
        "audit log",
        "log all prompts",
        "interaction logs",
        "telemetry",
        "traceability",
    ),
    "data_sovereignty": (
        "cross-border data sovereignty",
        "sovereign cloud",
        "on-shore",
        "australian data center",
        "cross-border",
        "stored within australia",
    ),
    "bias_testing": (
        "fairness",
        "bias testing",
        "discrimination",
        "demographic parity",
        "disparate impact",
    ),
    "model_inventory": (
        "ai inventory",
        "model registry",
        "use case register",
        "ai catalog",
        "model card",
    ),
}

FACET_TO_UNIFIED_CONTROLS: Dict[str, Sequence[str]] = {
    "human_approval_required": ("CTRL-FIN-APPROVAL-THRESHOLDS", "CTRL-GOV-OVERSIGHT"),
    "approval_threshold_defined": ("CTRL-FIN-APPROVAL-THRESHOLDS",),
    "pre_execution_block": ("CTRL-FIN-APPROVAL-THRESHOLDS", "CTRL-GOV-OVERSIGHT"),
    "zero_data_retention": ("CTRL-OPS-OUTSOURCING", "CTRL-PRIV-COLLECTION"),
    "prompt_logging": ("CTRL-TECH-OBSERVABILITY",),
    "data_sovereignty": ("CTRL-PRIV-CROSS-BORDER",),
    "bias_testing": ("CTRL-FAIR-BIAS-DETECTION",),
    "model_inventory": ("CTRL-GOV-FRAMEWORK",),
}

KNOWN_SHARED_INSTRUMENTS = (
    ("privacy act", "Privacy Act 1988 (Cth) / Australian Privacy Principles"),
    ("cps 230", "APRA CPS 230 (Operational Risk Management)"),
    ("cps 234", "APRA CPS 234 (Information Security)"),
    ("rg 271", "ASIC RG 271 (Internal Dispute Resolution)"),
    ("national ai ethics", "Australia's Artificial Intelligence Ethics Principles"),
)


def check_shared_library_duplicate(text: str) -> Optional[str]:
    lowered = text[:2000].lower()
    for needle, title in KNOWN_SHARED_INSTRUMENTS:
        if needle in lowered:
            return f"Document matches known shared regulation: '{title}'. Consider linking to the canonical shared catalogue."
    return None


def extract_enterprise_policy(
    *,
    tenant_id: str,
    name: str,
    text: str,
    version: str = "1.0.0",
    category: str = "general",
    authority_level: EnterpriseAuthorityLevel = EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    effective_date: Optional[datetime] = None,
    created_by: Optional[str] = None,
) -> EnterprisePolicy:
    if len(text.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("Policy text exceeds the 10 MB import limit")

    warnings: List[str] = []
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            warnings.append(
                "Potential embedded instruction detected and treated as inert policy text: "
                + pattern
            )

    dup_warning = check_shared_library_duplicate(text)
    if dup_warning:
        warnings.append(dup_warning)

    policy_id = str(uuid.uuid4())
    file_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    clauses: List[EnterpriseClause] = []
    for raw_clause in _split_clauses(text):
        clause_lower = raw_clause.lower()
        clause_id = _stable_clause_id(name, raw_clause)

        # Deterministic Category A: Absence of required control
        if ABSENCE_OF_CONTROL_PATTERN.search(raw_clause):
            clauses.append(
                EnterpriseClause(
                    clause_id=clause_id,
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    authority_level=authority_level,
                    control_facets=[],
                    thresholds_aud=[],
                    is_unmapped=True,
                    control_mappings=[],
                )
            )
            continue

        # Deterministic Category B (staff prohibition on activity): e.g. BASE-13
        if STAFF_PROHIBITION_PATTERN.search(raw_clause):
            clauses.append(
                EnterpriseClause(
                    clause_id=clause_id,
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    source_name=name,
                    text=raw_clause,
                    mandatory=True,
                    authority_level=authority_level,
                    control_facets=[],
                    thresholds_aud=[],
                    is_unmapped=True,
                    control_mappings=[],
                )
            )
            continue

        # Deterministic Category E: Policy exemption without active requirement
        if EXEMPTION_PATTERN.search(raw_clause) and not any(
            p in clause_lower for p in ("threshold", "require", "mandatory", "must")
        ):
            has_exc, exc_desc = _detect_exceptions(raw_clause)
            clauses.append(
                EnterpriseClause(
                    clause_id=clause_id,
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    authority_level=authority_level,
                    control_facets=[],
                    thresholds_aud=[],
                    is_unmapped=True,
                    control_mappings=[],
                    has_exception_clause=has_exc,
                    exception_description=exc_desc,
                )
            )
            continue

        # Deterministic Category F: Mere topic reference
        is_topic = bool(MERE_TOPIC_REFERENCE_PATTERN.search(raw_clause))
        has_mandatory_words = any(
            w in clause_lower
            for w in ("must", "shall", "is required", "are required", "mandatory")
        )
        if is_topic and not has_mandatory_words:
            clauses.append(
                EnterpriseClause(
                    clause_id=clause_id,
                    policy_id=policy_id,
                    tenant_id=tenant_id,
                    source_name=name,
                    text=raw_clause,
                    mandatory=False,
                    authority_level=authority_level,
                    control_facets=[],
                    thresholds_aud=[],
                    is_unmapped=True,
                    control_mappings=[],
                )
            )
            continue

        facets = [
            facet
            for facet, phrases in ENTERPRISE_FACET_PATTERNS.items()
            if any(phrase in clause_lower for phrase in phrases)
        ]
        thresholds = [
            float(match.replace(",", "")) for match in AUD_PATTERN.findall(raw_clause)
        ]
        if thresholds and "approval_threshold_defined" not in facets:
            facets.append("approval_threshold_defined")

        is_prohib_block = bool(PROHIBITION_BLOCK_PATTERN.search(raw_clause))
        if ("human_approval_required" in facets or is_prohib_block) and any(
            phrase in clause_lower
            for phrase in (
                "before payment",
                "before execution",
                "prior to payment",
                "prior to execution",
                "prior to",
                "must not execute",
                "cannot proceed",
                "prohibited prior to",
            )
        ):
            if "pre_execution_block" not in facets:
                facets.append("pre_execution_block")
            if "human_approval_required" not in facets and any(
                p in clause_lower for p in ("approval", "sign-off", "officer", "authoris")
            ):
                facets.append("human_approval_required")

        is_negated = bool(NEGATION_OR_EXEMPTION_PATTERN.search(raw_clause)) and not is_prohib_block

        # Generate candidate mappings to 33 Unified Controls only if clause is NOT a negation or exemption
        mappings: List[ClauseControlMapping] = []
        if not is_negated:
            for facet in facets:
                controls = FACET_TO_UNIFIED_CONTROLS.get(facet, ())
                for ctrl_id in controls:
                    mappings.append(
                        ClauseControlMapping(
                            tenant_id=tenant_id,
                            clause_id=clause_id,
                            control_id=ctrl_id,
                            relationship=MappingRelationship.FULL,
                            mapped_facets=[facet],
                            rationale=f"Clause contains facet '{facet}' associated with control {ctrl_id}.",
                            review_status=ClauseReviewStatus.PROPOSED,
                        )
                    )

        is_mand = bool(MANDATORY_PATTERN.search(raw_clause)) or is_prohib_block
        is_cond, cond_desc = _detect_conditions(raw_clause)
        has_exc, exc_desc = _detect_exceptions(raw_clause)

        clauses.append(
            EnterpriseClause(
                clause_id=clause_id,
                policy_id=policy_id,
                tenant_id=tenant_id,
                source_name=name,
                text=raw_clause,
                mandatory=is_mand,
                authority_level=authority_level,
                control_facets=facets,
                thresholds_aud=thresholds,
                is_unmapped=len(mappings) == 0,
                control_mappings=mappings,
                threshold_operator=_detect_threshold_operator(raw_clause),
                threshold_currency=_detect_threshold_currency(raw_clause),
                approval_timing=_detect_approval_timing(raw_clause),
                required_approval_role=_detect_approval_role(raw_clause),
                is_conditional=is_cond,
                condition_description=cond_desc,
                has_exception_clause=has_exc,
                exception_description=exc_desc,
                implementation_status=_detect_implementation_status(raw_clause),
            )
        )

    if not clauses:
        warnings.append("No policy clauses were extracted from the supplied text.")
    if not any(clause.mandatory for clause in clauses):
        warnings.append(
            "No mandatory policy language (for example, must/shall/required) was detected."
        )

    return EnterprisePolicy(
        policy_id=policy_id,
        tenant_id=tenant_id,
        name=name,
        category=category,
        authority_level=authority_level,
        version=version,
        status="active",
        effective_date=effective_date,
        file_sha256=file_sha256,
        clauses=clauses,
        warnings=warnings,
        created_at=utc_now(),
        created_by=created_by,
    )


def _valid_control_ids() -> Set[str]:
    """Return all valid control identifiers from the Unified Control Library and registered facet aliases."""
    from .catalog import load_unified_control_library

    valid_ids = {
        ctrl_id
        for ctrls in FACET_TO_UNIFIED_CONTROLS.values()
        for ctrl_id in ctrls
    }
    try:
        lib = load_unified_control_library()
        for ctrl in lib.controls:
            valid_ids.add(ctrl.control_id)
    except Exception:
        pass
    return valid_ids


def compute_baseline_fingerprint(
    *,
    tenant_id: str,
    name: str,
    version: str,
    revision: int,
    policy_ids: Sequence[str],
    confirmed_controls: Sequence[str],
    clauses: Sequence[EnterpriseClause],
    source_policy_versions: Optional[Dict[str, str]] = None,
) -> str:
    """Compute deterministic cryptographic SHA-256 fingerprint for baseline immutability."""
    fingerprint_obj = {
        "tenant_id": tenant_id,
        "name": name,
        "version": version,
        "revision": revision,
        "policy_ids": sorted(policy_ids),
        "source_policy_versions": dict(sorted((source_policy_versions or {}).items())),
        "confirmed_controls": sorted(confirmed_controls),
        "clause_ids": sorted([c.clause_id for c in clauses]),
        "clause_snapshots": [
            {
                "clause_id": c.clause_id,
                "text": c.text,
                "review_status": str(c.review_status),
                "is_unmapped": c.is_unmapped,
                "mandatory": c.mandatory,
                "control_facets": sorted(c.control_facets),
                "thresholds_aud": sorted(c.thresholds_aud),
                "control_mappings": [
                    {
                        "mapping_id": m.mapping_id,
                        "control_id": m.control_id,
                        "relationship": str(m.relationship),
                        "review_status": str(m.review_status),
                        "mapped_facets": sorted(getattr(m, "mapped_facets", []) or []),
                    }
                    for m in sorted(c.control_mappings, key=lambda x: x.mapping_id)
                ],
            }
            for c in sorted(clauses, key=lambda x: x.clause_id)
        ],
    }
    return hashlib.sha256(
        json.dumps(fingerprint_obj, sort_keys=True).encode("utf-8")
    ).hexdigest()


def verify_baseline_integrity(baseline: EnterpriseBaseline) -> bool:
    """Validate that the baseline's recorded cryptographic fingerprint matches its snapshot content."""
    if not baseline.baseline_sha256:
        return True
    if not baseline.clause_snapshots:
        return True
    expected = compute_baseline_fingerprint(
        tenant_id=baseline.tenant_id,
        name=baseline.name,
        version=baseline.version,
        revision=baseline.revision,
        policy_ids=baseline.policy_ids,
        confirmed_controls=baseline.confirmed_control_ids,
        clauses=baseline.clause_snapshots,
        source_policy_versions=baseline.source_policy_versions,
    )
    return secrets.compare_digest(baseline.baseline_sha256, expected)


def compile_enterprise_baseline(
    *,
    tenant_id: str,
    name: str,
    description: Optional[str] = None,
    policies: Sequence[EnterprisePolicy],
    version: str = "1.0.0",
    baseline_id: Optional[str] = None,
    revision: int = 1,
    created_by: Optional[str] = None,
    status: str = "active",
) -> EnterpriseBaseline:
    """Compile uploaded and reviewed enterprise policies into a versioned, immutable baseline.

    Workflow:
    Enterprise Policy Upload -> Clause Extraction -> Atomic Enterprise Requirements ->
    Candidate Unified Control Mapping -> Human Review -> Versioned Enterprise Baseline.
    """
    for p in policies:
        if p.tenant_id != tenant_id:
            raise ValueError(f"Policy '{p.policy_id}' does not belong to tenant '{tenant_id}'")
        for c in p.clauses:
            if c.tenant_id != tenant_id or c.policy_id != p.policy_id:
                raise ValueError(
                    f"Clause '{c.clause_id}' has inconsistent tenant or policy ownership reference"
                )

    policy_ids = [p.policy_id for p in policies]
    policy_status_by_id = {p.policy_id: p.status for p in policies}
    all_clauses = [c for p in policies for c in p.clauses]
    warnings: List[str] = []
    source_policy_versions = {p.policy_id: p.version for p in policies}

    # Baseline Eligibility Hardening (Step 6)
    if not policies or not all_clauses:
        if status == "active":
            raise ValueError("Cannot compile an active baseline from empty policy input")
        status = "draft"

    has_approved = any(
        c.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
        for c in all_clauses
    )
    if not has_approved:
        if status == "active":
            status = "draft"
            warnings.append(
                "Baseline compiled with 'draft' status: policies contain wholly pending or rejected content "
                "with no approved or confirmed clauses. Draft baselines are not eligible for confirmed assessment."
            )

    # 1. Deduplication: detect duplicate requirements across policies
    seen_norm_texts: Dict[str, str] = {}
    for c in all_clauses:
        norm = " ".join(c.text.lower().split())
        if norm in seen_norm_texts:
            warnings.append(
                f"Duplicate requirement detected: clause in '{c.source_name}' duplicates requirement in '{seen_norm_texts[norm]}'."
            )
        else:
            seen_norm_texts[norm] = c.source_name

    # 2. Policy Versioning & Status: detect superseded or retired policies
    policy_names: Dict[str, List[EnterprisePolicy]] = {}
    for p in policies:
        policy_names.setdefault(p.name, []).append(p)
    for pname, plist in policy_names.items():
        if len(plist) > 1:
            vers = [p.version for p in plist]
            warnings.append(
                f"Multiple versions of policy '{pname}' detected in baseline: {vers}. Ensure superseded versions are retired."
            )
        for p in plist:
            if p.status in {"superseded", "retired"}:
                warnings.append(
                    f"Policy '{p.name}' (v{p.version}) has status '{p.status}'. Superseded policies should be excluded from active baselines."
                )

    # 3. Classify clauses and control mappings (Section 5: Separate Approval Decisions)
    valid_controls = _valid_control_ids()
    approved_clause_ids: List[str] = []
    confirmed_controls: Set[str] = set()
    pending_clause_ids: List[str] = []
    unmapped_clause_ids: List[str] = []

    for c in all_clauses:
        pol_status = policy_status_by_id.get(c.policy_id, "active")
        is_superseded = pol_status in {"superseded", "retired"} or getattr(c, "status", None) in {
            "superseded",
            "retired",
        }
        is_approved = (
            not is_superseded
            and c.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
        )
        has_mappings = len(c.control_mappings) > 0

        if is_approved:
            approved_clause_ids.append(c.clause_id)

        if not has_mappings:
            unmapped_clause_ids.append(c.clause_id)
        elif not is_approved and c.review_status != ClauseReviewStatus.REJECTED:
            pending_clause_ids.append(c.clause_id)

        # A Control Mapping enters confirmed_control_ids ONLY when:
        # 1. Source clause is approved or confirmed (and not superseded/retired)
        # 2. Specific mapping is independently approved or confirmed
        # 3. Mapping relationship is FULL or PARTIAL (not non-equivalent/missing/undetermined)
        # 4. Mapping references a valid control in the Unified Control Library
        # 5. Tenant and clause ownership references are internally consistent
        for m in c.control_mappings:
            mapping_is_approved = m.review_status in {
                ClauseReviewStatus.APPROVED,
                ClauseReviewStatus.CONFIRMED,
            }
            valid_relationship = m.relationship in {
                MappingRelationship.FULL,
                MappingRelationship.PARTIAL,
            }
            valid_control = bool(m.control_id and m.control_id in valid_controls)
            consistent_refs = (m.tenant_id == tenant_id and m.clause_id == c.clause_id)

            if (
                is_approved
                and mapping_is_approved
                and valid_relationship
                and valid_control
                and consistent_refs
            ):
                confirmed_controls.add(m.control_id)

    # 4. Inconsistency and Conflict Detection (internal review items, not statutory breaches)
    conflicts: List[GapRecord] = []
    mandatory_clauses = [c for c in all_clauses if c.mandatory]
    observed_thresholds = sorted(
        {t for c in mandatory_clauses for t in c.thresholds_aud}
    )
    if len(observed_thresholds) > 1:
        conflicts.append(
            GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.CONTROL_CONFLICT,
                title="Enterprise policies contain conflicting AUD approval thresholds",
                severity="high",
                missing_facets=["single_authoritative_threshold"],
                recommendation=f"Reconcile contradictory thresholds across policies: {observed_thresholds}.",
                evidence_required=["Approved delegated-authority schedule"],
                source_type="internal_conflict",
            )
        )

    # 5. Build immutable clause snapshots
    clause_snapshots = [c.model_copy(deep=True) for c in all_clauses]

    # 6. Compute cryptographic SHA-256 fingerprint for immutability
    baseline_sha256 = compute_baseline_fingerprint(
        tenant_id=tenant_id,
        name=name,
        version=version,
        revision=revision,
        policy_ids=policy_ids,
        confirmed_controls=list(confirmed_controls),
        clauses=all_clauses,
        source_policy_versions=source_policy_versions,
    )

    return EnterpriseBaseline(
        baseline_id=baseline_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=description,
        version=version,
        revision=revision,
        policy_ids=policy_ids,
        source_policy_versions=source_policy_versions,
        clause_snapshots=clause_snapshots,
        approved_clause_ids=approved_clause_ids,
        confirmed_control_ids=sorted(confirmed_controls),
        pending_clause_ids=pending_clause_ids,
        unmapped_clause_ids=unmapped_clause_ids,
        conflicts=conflicts,
        warnings=warnings,
        baseline_sha256=baseline_sha256,
        status=status,
        created_at=utc_now(),
        created_by=created_by,
    )


def assess_enterprise_policy_gaps(
    *,
    tenant_id: str,
    use_case: Optional[BankingUseCase] = None,
    policies: Sequence[EnterprisePolicy],
    question_bank: QuestionBank,
    regulatory_pack: RegulatoryPack,
    baseline_id: Optional[str] = None,
    full_regulatory_scope: bool = False,
) -> PolicyGapAssessment:
    if use_case is None:
        use_case = BankingUseCase.enterprise_baseline()

    all_clauses: List[EnterpriseClause] = [
        clause for policy in policies for clause in policy.clauses
    ]
    mandatory_clauses = [clause for clause in all_clauses if clause.mandatory]

    policy_gaps: List[GapRecord] = []
    questionnaire_gaps: List[GapRecord] = []
    conflicts: List[GapRecord] = []
    evidence_gaps: List[GapRecord] = []
    gaps_by_layer: Dict[str, List[GapRecord]] = {}

    # Unified Controls and facets addressed by the uploaded policies
    addressed_controls = {
        m.control_id
        for clause in all_clauses
        for m in clause.control_mappings
        if m.control_id
    }
    addressed_facets = {
        facet
        for clause in all_clauses
        for facet in clause.control_facets
    }
    has_general_policy = any(
        (p.category or "").lower() in ("general", "governance", "all")
        for p in policies
    )

    # 1. Regulatory-to-Policy Gaps:
    # Crucial boundary: Only evaluate regulatory obligations that are relevant to the scope
    # of the uploaded policies (by matching mapped controls, facets, or general category),
    # unless full_regulatory_scope is explicitly requested.
    # Single-domain policies must never generate statutory non-compliance findings for
    # completely unrelated regulatory obligations.
    for obligation in regulatory_pack.obligations:
        applicability = decide_applicability(obligation, use_case)
        if applicability.status is not ApplicabilityStatus.APPLICABLE:
            continue

        if not full_regulatory_scope and not has_general_policy:
            is_relevant = (
                obligation.control_id in addressed_controls
                or any(f in addressed_facets for f in obligation.coverage_facets)
            )
            if not is_relevant:
                continue

        missing_facets = []
        for facet in obligation.coverage_facets:
            phrases = [p.lower() for p in obligation.facet_keywords.get(facet, [])]
            covered = False
            for clause in all_clauses:
                t = clause.text.lower()
                if any(phrase in t for phrase in phrases):
                    covered = True
                    break
                if facet in clause.control_facets:
                    covered = True
                    break
            if not covered:
                missing_facets.append(facet)

        if missing_facets:
            bucket = authority_layer_bucket(obligation.authority)
            gap = GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.ENTERPRISE_POLICY,
                title="Enterprise policy does not cover a required regulatory obligation",
                severity=_severity(obligation),
                obligation_id=obligation.obligation_id,
                missing_facets=missing_facets,
                recommendation=(
                    f"Update enterprise policies to explicitly address {obligation.instrument} {obligation.provision} "
                    f"({obligation.title}): missing facets {missing_facets}."
                ),
                evidence_required=[
                    "Updated enterprise policy",
                    "Executive risk committee approval",
                ],
            )
            gaps_by_layer.setdefault(bucket, []).append(gap)
            if obligation.authority in {
                Authority.BINDING,
                Authority.ENFORCEABLE_GUIDANCE,
            }:
                policy_gaps.append(gap)

    # 2. Policy-to-Questionnaire Gaps: Does questionnaire test mandatory enterprise standards?
    for clause in mandatory_clauses:
        missing = [
            facet
            for facet in clause.control_facets
            if not _questionnaire_covers_generic_facet(
                facet,
                question_bank,
                PolicyClause(
                    clause_id=clause.clause_id,
                    source_name=clause.source_name,
                    text=clause.text,
                    mandatory=clause.mandatory,
                    control_facets=clause.control_facets,
                    thresholds_aud=clause.thresholds_aud,
                ),
            )
        ]
        if missing:
            # Check if voluntary framework
            is_voluntary = (
                clause.authority_level == EnterpriseAuthorityLevel.INDUSTRY_FRAMEWORK
            )
            severity = "low" if is_voluntary else (
                "high"
                if any("approval" in f or "execution" in f or "retention" in f for f in missing)
                else "medium"
            )
            questionnaire_gaps.append(
                GapRecord(
                    gap_id=str(uuid.uuid4()),
                    gap_type=GapType.QUESTIONNAIRE,
                    title="Questionnaire does not test a mandatory enterprise-policy control",
                    severity=severity,
                    policy_clause_id=clause.clause_id,
                    missing_facets=missing,
                    recommendation=(
                        f"Add a question testing '{clause.source_name}' requirements ({missing})."
                    ),
                    evidence_required=[
                        "Approved policy clause",
                        "Question-to-policy mapping review",
                    ],
                )
            )

        evidence_gaps.append(
            GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.IMPLEMENTATION_EVIDENCE,
                title="Mandatory policy control has not been implementation-tested",
                severity="medium",
                policy_clause_id=clause.clause_id,
                missing_facets=list(clause.control_facets),
                recommendation="Connect the control to DeepAudit evidence review or behavioural testing.",
                evidence_required=[
                    "System configuration",
                    "Execution trace",
                    "Control test result",
                ],
            )
        )

    # 3. Control Conflict Detection: Multiple differing AUD thresholds across baseline
    observed_thresholds = sorted(
        {
            threshold
            for clause in mandatory_clauses
            for threshold in clause.thresholds_aud
        }
    )
    if len(observed_thresholds) > 1:
        conflicts.append(
            GapRecord(
                gap_id=str(uuid.uuid4()),
                gap_type=GapType.CONTROL_CONFLICT,
                title="Enterprise policies contain conflicting AUD approval thresholds",
                severity="high",
                missing_facets=["single_authoritative_threshold"],
                recommendation=f"Reconcile contradictory thresholds across policies: {observed_thresholds}.",
                evidence_required=["Approved delegated-authority schedule"],
            )
        )
    elif observed_thresholds and use_case.approval_threshold_aud is not None:
        policy_threshold = observed_thresholds[0]
        if policy_threshold != use_case.approval_threshold_aud:
            conflicts.append(
                GapRecord(
                    gap_id=str(uuid.uuid4()),
                    gap_type=GapType.CONTROL_CONFLICT,
                    title="Configured approval threshold conflicts with enterprise policy",
                    severity="critical",
                    missing_facets=["approval_threshold_aligned"],
                    recommendation=(
                        f"Align system threshold AUD {use_case.approval_threshold_aud:g} to policy "
                        f"threshold AUD {policy_threshold:g}."
                    ),
                    evidence_required=[
                        "Delegated-authority policy",
                        "Production configuration",
                    ],
                )
            )

    all_policy_clauses = [
        PolicyClause(
            clause_id=c.clause_id,
            source_name=c.source_name,
            text=c.text,
            mandatory=c.mandatory,
            control_facets=c.control_facets,
            thresholds_aud=c.thresholds_aud,
        )
        for c in all_clauses
    ]

    all_warnings = [w for p in policies for w in p.warnings]

    return PolicyGapAssessment(
        assessment_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        policy_pack_id=policies[0].policy_id if policies else "empty_policy_pack",
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        routing_snapshot_id=question_bank.routing_metadata.get("routing_snapshot_id"),
        selected_question_ids=[item.question_id for item in question_bank.questions],
        policy_gaps=policy_gaps,
        questionnaire_gaps=questionnaire_gaps,
        control_conflicts=conflicts,
        implementation_evidence_gaps=evidence_gaps,
        gaps_by_authority_layer=gaps_by_layer,
        policy_clauses=all_policy_clauses,
        warnings=all_warnings,
        enterprise_baseline_id=baseline_id,
        enterprise_policy_ids=[p.policy_id for p in policies],
    )
