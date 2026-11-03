"""Enterprise policy extraction and two-way gap analysis.

Policy text is always treated as untrusted data.  Extraction is deterministic;
the parser records prompt-injection-like phrases instead of following them.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Sequence

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
    r"\b(must|shall|required to|requires?|may not|must not|is prohibited|will not)\b",
    re.IGNORECASE,
)
AUD_PATTERN = re.compile(
    r"(?:AUD\s*\$?\s*|\$\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d,])",
    re.IGNORECASE,
)


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
    "human_approval_required": ("human approval", "human oversight", "manual review"),
    "approval_threshold_defined": ("threshold", "aud", "$500", "500"),
    "pre_execution_block": (
        "before execution",
        "prevent execution",
        "cannot proceed",
        "override",
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
        if "human_approval_required" in facets and any(
            phrase in clause_lower
            for phrase in (
                "before payment",
                "before execution",
                "prior to payment",
                "must not execute",
            )
        ):
            if "pre_execution_block" not in facets:
                facets.append("pre_execution_block")
        clauses.append(
            PolicyClause(
                clause_id=_stable_clause_id(name, raw_clause),
                source_name=name,
                text=raw_clause,
                mandatory=bool(MANDATORY_PATTERN.search(raw_clause)),
                control_facets=facets,
                thresholds_aud=thresholds,
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
            if any(
                term in question.question_text.lower()
                for term in ("approval", "refund", "payment")
            )
            for match in AUD_PATTERN.findall(question.question_text)
        }
        return required_amounts.issubset(assessed_amounts)
    keywords = QUESTION_KEYWORDS.get(facet, (facet.replace("_", " "),))
    for question in bank.questions:
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
        "sovereignty",
        "on-shore",
        "australian data center",
        "sydney",
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
        if "human_approval_required" in facets and any(
            phrase in clause_lower
            for phrase in (
                "before payment",
                "before execution",
                "prior to payment",
                "must not execute",
            )
        ):
            if "pre_execution_block" not in facets:
                facets.append("pre_execution_block")

        clause_id = _stable_clause_id(name, raw_clause)

        # Generate candidate mappings to 33 Unified Controls
        mappings: List[ClauseControlMapping] = []
        for facet in facets:
            controls = FACET_TO_UNIFIED_CONTROLS.get(facet, ())
            for ctrl_id in controls:
                mappings.append(
                    ClauseControlMapping(
                        tenant_id=tenant_id,
                        clause_id=clause_id,
                        control_id=ctrl_id,
                        relationship=MappingRelationship.FULL,
                        rationale=f"Clause contains facet '{facet}' associated with control {ctrl_id}.",
                        review_status=ClauseReviewStatus.PROPOSED,
                    )
                )

        clauses.append(
            EnterpriseClause(
                clause_id=clause_id,
                policy_id=policy_id,
                tenant_id=tenant_id,
                source_name=name,
                text=raw_clause,
                mandatory=bool(MANDATORY_PATTERN.search(raw_clause)),
                authority_level=authority_level,
                control_facets=facets,
                thresholds_aud=thresholds,
                control_mappings=mappings,
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


def assess_enterprise_policy_gaps(
    *,
    tenant_id: str,
    use_case: Optional[BankingUseCase] = None,
    policies: Sequence[EnterprisePolicy],
    question_bank: QuestionBank,
    regulatory_pack: RegulatoryPack,
    baseline_id: Optional[str] = None,
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

    # 1. Regulatory-to-Policy Gaps: Does enterprise baseline cover applicable statutory obligations?
    for obligation in regulatory_pack.obligations:
        applicability = decide_applicability(obligation, use_case)
        if applicability.status is not ApplicabilityStatus.APPLICABLE:
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
