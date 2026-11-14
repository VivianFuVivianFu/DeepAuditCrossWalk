"""Enterprise Requirement Reconciliation Engine & Effective Baseline Composer (E1).

Implements a deterministic, two-stage reconciliation architecture:
- Stage A: Candidate Relationship Generation (control mappings, facets, citations, topics).
- Stage B: Multi-Dimension Relationship Validation (scope, subject, actor, polarity,
  modality, threshold value & operator boundary, currency, timing, conditions,
  exceptions, authority level, and facet completeness).
- Human Review & Staleness Detection: Version-bound ReconciliationDecision lifecycle.
- Effective Assessment Baseline Composition: Auditable, reproducible composition of
  applicable Shared Regulatory Library obligations + approved Enterprise Baseline
  requirements without silently merging, discarding, weakening, or misclassifying
  requirements.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .applicability import decide_applicability, select_applicable_obligations
from .catalog import (
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_unified_control_library,
)
from .models import (
    ApplicabilityStatus,
    AtomicObligation,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EffectiveAssessmentBaseline,
    EffectiveBaselineRequirementItem,
    EffectiveBaselineSourceReference,
    EffectiveBaselineUnresolvedItem,
    EffectivePresentationGroup,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    ObligationControlMappingCatalogue,
    ReconciliationAuditEntry,
    ReconciliationDecision,
    ReconciliationDecisionStatus,
    ReconciliationDimensionComparison,
    ReconciliationRelationship,
    RegulatoryPack,
    UnifiedControlLibrary,
)
from .policy import (
    ABSENCE_OF_CONTROL_PATTERN,
    PROHIBITION_BLOCK_PATTERN,
    STAFF_PROHIBITION_PATTERN,
    _detect_approval_role,
    _detect_approval_timing,
    _detect_conditions,
    _detect_exceptions,
    _detect_threshold_currency,
    _detect_threshold_operator,
    verify_baseline_integrity,
)


# ─────────────────────────────────────────────────────────────────────────────
# Control Alias & Domain Equivalence Tables (Stage A Candidate Linking Only)
# ─────────────────────────────────────────────────────────────────────────────

# Bridges policy.py extractor control IDs to Unified Control Library IDs
CONTROL_ID_ALIASES: Dict[str, Tuple[str, ...]] = {
    "CTRL-FIN-APPROVAL-THRESHOLDS": (
        "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        "CTRL-HUMAN-OVERSIGHT",
    ),
    "CTRL-DELEGATED-AUTHORITY-THRESHOLD": (
        "CTRL-FIN-APPROVAL-THRESHOLDS",
        "CTRL-HUMAN-OVERSIGHT",
    ),
    "CTRL-GOV-OVERSIGHT": ("CTRL-HUMAN-OVERSIGHT",),
    "CTRL-HUMAN-OVERSIGHT": ("CTRL-GOV-OVERSIGHT", "CTRL-FIN-APPROVAL-THRESHOLDS"),
    "CTRL-PRIV-COLLECTION": ("CTRL-PRIV-COLLECTION", "CTRL-PRIV-USE-DISCLOSURE"),
    "CTRL-PRIV-CROSS-BORDER": ("CTRL-PRIV-CROSS-BORDER", "CTRL-MSP-NOTIFICATION"),
    "CTRL-FAIR-BIAS-DETECTION": ("CTRL-AI-IMPACT-ASSESSMENT", "CTRL-CREDIT-UNSUITABILITY"),
    "CTRL-TECH-OBSERVABILITY": ("CTRL-AI-DRIFT-MONITORING", "CTRL-PRIV-SECURITY-RETENTION"),
    "CTRL-OPS-OUTSOURCING": ("CTRL-THIRD-PARTY-AI", "CTRL-OPS-RISK"),
    "CTRL-GOV-FRAMEWORK": ("CTRL-AI-GOV-ACCOUNTABILITY", "CTRL-RISK-FRAMEWORK", "CTRL-ISO-AIMS"),
    "CTRL-SEC-INCIDENT": ("CTRL-SEC-INCIDENT", "CTRL-PRIV-NDB-S26WE"),
    "CTRL-COMPLAINTS-IDR": ("CTRL-IDR-HANDLING", "CTRL-IDR-SYSTEMIC"),
}

ENTERPRISE_ONLY_CONTROL_IDS: Set[str] = {
    "CTRL-FIN-APPROVAL-THRESHOLDS",
    "CTRL-DELEGATED-AUTHORITY-THRESHOLD",
}

AMBIGUOUS_CLAUSE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\bas\s+determined\s+from\s+time\s+to\s+time\b", re.IGNORECASE),
    re.compile(r"\bin\s+accordance\s+with\s+schedule\s+[a-z0-9]+\b", re.IGNORECASE),
    re.compile(r"\bappropriate\s+governance\s+arrangements\s+shall\s+be\s+applied\b", re.IGNORECASE),
    re.compile(r"\bwhere\s+deemed\s+appropriate\s+by\s+management\b", re.IGNORECASE),
    re.compile(r"\bsubject\s+to\s+unquantified\s+discretion\b", re.IGNORECASE),
    re.compile(r"\bas\s+reasonably\s+practicable\s+without\s+defined\s+criteria\b", re.IGNORECASE),
)

CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?:\b(AUD|USD|EUR|GBP|NZD)\s*\$?\s*|A\$\s*|US\$\s*|\$\s*)(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)

TIMEFRAME_PATTERN = re.compile(
    r"\b(?:within|up\s+to|no\s+later\s+than|after|every)\s+(\d+)\s*(hours?|days?|business\s+days?)\b",
    re.IGNORECASE,
)

SCOPE_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        "refunds",
        re.compile(
            r"\b(refunds?|reimbursements?|chargebacks?|dispute\s+credits?|fee\s+waivers?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credit_decisions",
        re.compile(
            r"\b(credit\s+suitability|unsuitability|responsible\s+lending|loan\s+applications?|credit\s+decisions?|creditworthiness|nccp)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "complaints_idr",
        re.compile(
            r"\b(internal\s+dispute\s+resolution|\bidr\b|afca|rg\s*271|regulated\s+complaints?|complaint\s+resolution)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cross_border_disclosure",
        re.compile(
            r"\b(cross[-\s]border|overseas\s+recipients?|offshore|data\s+residency|app\s*8|16c)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "personal_information_collection",
        re.compile(
            r"\b(collect(?:ing|ion)?\s+personal\s+information|sensitive\s+information|biometrics?|app\s*3)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "privacy_impact_governance",
        re.compile(
            r"\b(privacy\s+impact\s+assessments?|\bpias?\b|privacy\s+by\s+design|privacy\s+policy|privacy\s+owner|app\s*1)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "security_incident_notification",
        re.compile(
            r"\b(information\s+security\s+incidents?|cyber\s+incidents?|notifiable\s+data\s+breach|\bndb\b|72[-\s]hours?|cps\s*234)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "third_party_service_providers",
        re.compile(
            r"\b(material\s+service\s+providers?|\bmsps?\b|third[-\s]party\s+ai|fourth[-\s]party|cps\s*230)\b",
            re.IGNORECASE,
        ),
    ),
)

ACTOR_RANK: Dict[str, int] = {
    "team_leader": 1,
    "senior_manager": 2,
    "authorised_officer": 3,
    "responsible_manager": 4,
    "executive": 5,
    "board_or_committee": 6,
    "dual_approval": 7,
}


def compute_clause_sha256(clause: EnterpriseClause) -> str:
    """Compute a deterministic SHA-256 fingerprint of an EnterpriseClause."""
    approved_mappings = sorted(
        [
            {
                "control_id": m.control_id,
                "relationship": m.relationship.value
                if hasattr(m.relationship, "value")
                else str(m.relationship),
                "mapped_facets": sorted(m.mapped_facets),
                "review_status": m.review_status.value
                if hasattr(m.review_status, "value")
                else str(m.review_status),
            }
            for m in (clause.control_mappings or [])
        ],
        key=lambda item: (item["control_id"], item["review_status"]),
    )
    payload = {
        "clause_id": clause.clause_id,
        "policy_id": clause.policy_id,
        "text": " ".join((clause.text or "").split()),
        "mandatory": bool(clause.mandatory),
        "authority_level": clause.authority_level.value
        if hasattr(clause.authority_level, "value")
        else str(clause.authority_level),
        "review_status": clause.review_status.value
        if hasattr(clause.review_status, "value")
        else str(clause.review_status),
        "control_facets": sorted(clause.control_facets or []),
        "thresholds_aud": [float(x) for x in (clause.thresholds_aud or [])],
        "threshold_operator": clause.threshold_operator,
        "threshold_currency": clause.threshold_currency,
        "approval_timing": clause.approval_timing,
        "required_approval_role": clause.required_approval_role,
        "is_conditional": bool(clause.is_conditional),
        "condition_description": clause.condition_description,
        "has_exception_clause": bool(clause.has_exception_clause),
        "exception_description": clause.exception_description,
        "control_mappings": approved_mappings,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _deterministic_reconciliation_id(
    tenant_id: str,
    baseline_id: str,
    enterprise_clause_id: str,
    external_obligation_id: Optional[str],
    peer_enterprise_clause_id: Optional[str] = None,
) -> str:
    raw = (
        f"{tenant_id}|{baseline_id}|{enterprise_clause_id}|"
        f"{external_obligation_id or 'NONE'}|{peer_enterprise_clause_id or 'NONE'}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
    return f"REC-{digest}"


def _extract_currency_and_amounts(text: str) -> List[Tuple[str, float]]:
    results: List[Tuple[str, float]] = []
    for match in CURRENCY_AMOUNT_PATTERN.finditer(text or ""):
        raw_full = match.group(0).upper()
        code = (match.group(1) or "").upper()
        if not code:
            if "US$" in raw_full:
                code = "USD"
            else:
                code = "AUD"
        val_str = match.group(2).replace(",", "")
        try:
            results.append((code, float(val_str)))
        except ValueError:
            continue
    return results


def _extract_timeframe_hours(text: str) -> Optional[float]:
    match = TIMEFRAME_PATTERN.search(text or "")
    if not match:
        return None
    val = float(match.group(1))
    unit = match.group(2).lower()
    if "day" in unit:
        return val * 24.0
    return val


def _detect_operational_scopes(text: str) -> List[str]:
    scopes: List[str] = []
    for label, pattern in SCOPE_PATTERNS:
        if pattern.search(text or ""):
            scopes.append(label)
    return scopes


def _normalize_actor(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    lower = role.strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
    if "dual" in lower or "two_up" in lower or "four_eyes" in lower:
        return "dual_approval"
    if "board" in lower or "committee" in lower:
        return "board_or_committee"
    if "executive" in lower:
        return "executive"
    if "responsible_manager" in lower:
        return "responsible_manager"
    if "authorised_officer" in lower or "authorized_officer" in lower:
        return "authorised_officer"
    if "senior_manager" in lower or "head_of" in lower or "risk_lead" in lower:
        return "senior_manager"
    if "team_leader" in lower or "supervisor" in lower or "line_manager" in lower or "manager" in lower:
        return "team_leader"
    return lower


def _detect_external_actor(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if "responsible manager" in lowered:
        return "responsible_manager"
    if "board" in lowered or "board risk committee" in lowered:
        return "board_or_committee"
    return _normalize_actor(_detect_approval_role(text or ""))


def _detect_external_timing(obligation: AtomicObligation) -> Optional[str]:
    combined = f"{obligation.title} {obligation.concise_obligation_summary} {obligation.control_objective}"
    timing = _detect_approval_timing(combined)
    if timing:
        return timing
    lowered = combined.lower()
    if any(
        phrase in lowered
        for phrase in (
            "at or before",
            "before disclosing",
            "before collecting",
            "prior to deployment",
            "before consequential",
            "human-in-the-loop",
            "override capability",
            "kill-switch",
        )
    ):
        return "pre_execution"
    return None


def _is_ambiguous_clause(clause: EnterpriseClause) -> bool:
    for pattern in AMBIGUOUS_CLAUSE_PATTERNS:
        if pattern.search(clause.text or ""):
            return True
    return False


def _detect_action_polarity(clause: EnterpriseClause) -> str:
    text = clause.text or ""
    if ABSENCE_OF_CONTROL_PATTERN.search(text):
        return "absence_of_control"
    if PROHIBITION_BLOCK_PATTERN.search(text) or STAFF_PROHIBITION_PATTERN.search(text) or re.search(
        r"\b(must\s+not|shall\s+not|prohibited\s+from|never\s+be)\b",
        text,
        re.IGNORECASE,
    ):
        return "prohibition"
    if not clause.mandatory:
        return "permissive"
    return "positive_requirement"


def _expand_control_ids(control_ids: Iterable[str]) -> Set[str]:
    expanded: Set[str] = set()
    for cid in control_ids:
        if not cid:
            continue
        expanded.add(cid)
        for alias in CONTROL_ID_ALIASES.get(cid, ()):
            expanded.add(alias)
    return expanded


# ─────────────────────────────────────────────────────────────────────────────
# Stage B: Multi-Dimension Relationship Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_candidate_relationship(
    *,
    clause: EnterpriseClause,
    obligation: Optional[AtomicObligation],
    regulatory_pack: RegulatoryPack,
    enterprise_baseline: EnterpriseBaseline,
    policy_version: str = "1.0.0",
    policy_name: Optional[str] = None,
    stage_a_reason: str = "",
) -> ReconciliationDecision:
    """Stage B: Validate the relationship between an EnterpriseClause and an AtomicObligation.

    Compares scope, subject, actor, action polarity, modality, numeric threshold &
    operator boundary, currency, approval timing, conditions, exceptions, authority,
    and facet completeness. Never promotes candidate similarity directly to an
    approved reconciliation decision.
    """
    uncertainties: List[str] = []
    clause_sha = compute_clause_sha256(clause)
    polarity = _detect_action_polarity(clause)

    # Extract clause currency & threshold details from both structured fields and raw text
    raw_amounts = _extract_currency_and_amounts(clause.text)
    ent_currency = clause.threshold_currency or (
        raw_amounts[0][0] if raw_amounts else (_detect_threshold_currency(clause.text) if clause.thresholds_aud else None)
    )
    ent_threshold = (
        clause.thresholds_aud[0]
        if clause.thresholds_aud
        else (raw_amounts[0][1] if raw_amounts else None)
    )
    ent_operator = clause.threshold_operator or (
        _detect_threshold_operator(clause.text) if ent_threshold is not None else None
    )
    ent_timing = clause.approval_timing or _detect_approval_timing(clause.text)
    ent_actor = _normalize_actor(
        clause.required_approval_role or _detect_approval_role(clause.text)
    )
    ent_scopes = _detect_operational_scopes(clause.text)

    # Non-rejected and approved control mappings on the clause
    non_rejected_mappings = [
        m
        for m in (clause.control_mappings or [])
        if m.review_status != ClauseReviewStatus.REJECTED
    ]
    approved_mappings = [
        m
        for m in non_rejected_mappings
        if m.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
    ]
    proposed_mappings = [
        m
        for m in non_rejected_mappings
        if m.review_status == ClauseReviewStatus.PROPOSED
    ]

    # Case 0: No external obligation (either Additional Enterprise Requirement or Unmapped)
    if obligation is None:
        is_ambiguous = _is_ambiguous_clause(clause)
        if is_ambiguous:
            uncertainties.append(
                "Enterprise clause contains ambiguous or unquantified governance phrasing requiring human interpretation."
            )
            rel = ReconciliationRelationship.UNDETERMINED
            status = ReconciliationDecisionStatus.NEEDS_REVIEW
            rationale = (
                "Clause has no matched external obligation and uses ambiguous phrasing "
                "that cannot be deterministically classified without human review."
            )
        elif approved_mappings or (
            clause.control_facets
            and any(
                cid in ENTERPRISE_ONLY_CONTROL_IDS
                for cid in [m.control_id for m in non_rejected_mappings]
            )
        ):
            rel = ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT
            status = ReconciliationDecisionStatus.PROPOSED
            rationale = (
                f"Enterprise clause '{clause.clause_id}' introduces an internal enterprise "
                f"requirement ({', '.join(clause.control_facets) or 'enterprise governance control'}) "
                "with no direct external regulatory obligation counterpart in the Shared Regulatory Library."
            )
        elif non_rejected_mappings and not approved_mappings:
            uncertainties.append(
                "Candidate control mapping is still in 'proposed' status and has not been human-approved."
            )
            rel = ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT
            status = ReconciliationDecisionStatus.PROPOSED
            rationale = (
                f"Enterprise clause '{clause.clause_id}' defines an internal requirement with a "
                "proposed control mapping and no external regulatory obligation counterpart."
            )
        else:
            rel = ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
            status = ReconciliationDecisionStatus.PROPOSED
            rationale = (
                f"Approved enterprise clause '{clause.clause_id}' has no canonical Unified Control "
                "mapping and no reliable relationship to any external obligation in the Shared Regulatory Library. "
                "Preserved as an unmapped enterprise requirement."
            )

        dim = ReconciliationDimensionComparison(
            scope_match="enterprise_only",
            enterprise_scope=",".join(ent_scopes) if ent_scopes else "enterprise_general",
            external_scope=None,
            subject_match="enterprise_only",
            actor_comparison="enterprise_only" if ent_actor else "not_applicable",
            enterprise_actor=ent_actor,
            action_polarity=polarity,
            modality_comparison="enterprise_mandatory" if clause.mandatory else "enterprise_discretionary",
            threshold_comparison="enterprise_only" if ent_threshold is not None else "not_applicable",
            enterprise_threshold=ent_threshold,
            enterprise_operator=ent_operator,
            enterprise_currency=ent_currency,
            timing_comparison="enterprise_only" if ent_timing else "not_applicable",
            enterprise_timing=ent_timing,
            condition_status="conditional_enterprise" if clause.is_conditional else "unconditional",
            exception_status="enterprise_exception_weakens" if clause.has_exception_clause else "no_exceptions",
            authority_comparison=f"enterprise_only_{clause.authority_level.value}",
            shared_control_ids=[],
            shared_facets=[],
            enterprise_only_facets=sorted(set(clause.control_facets or [])),
            external_unaddressed_facets=[],
        )
        return ReconciliationDecision(
            reconciliation_id=_deterministic_reconciliation_id(
                clause.tenant_id, enterprise_baseline.baseline_id, clause.clause_id, None
            ),
            tenant_id=clause.tenant_id,
            enterprise_clause_id=clause.clause_id,
            external_obligation_id=None,
            regulatory_pack_id=regulatory_pack.pack_id,
            regulatory_pack_version=regulatory_pack.version,
            enterprise_policy_id=clause.policy_id,
            enterprise_policy_name=policy_name or clause.source_name,
            enterprise_policy_version=policy_version,
            enterprise_authority_level=clause.authority_level.value,
            enterprise_clause_sha256=clause_sha,
            enterprise_baseline_id=enterprise_baseline.baseline_id,
            enterprise_baseline_version=enterprise_baseline.version,
            enterprise_baseline_revision=enterprise_baseline.revision,
            enterprise_baseline_sha256=enterprise_baseline.baseline_sha256 or "",
            stage_a_candidate_reason=stage_a_reason or "No external obligation candidate matched.",
            proposed_relationship=rel,
            validated_relationship=rel,
            decision_status=status,
            supporting_passages=[clause.text],
            comparison_rationale=rationale,
            dimension_comparison=dim,
            uncertainties=uncertainties,
        )

    # ── External obligation is present: gather external metadata ──
    source_lookup = {s.source_id: s for s in regulatory_pack.sources}
    ext_source = source_lookup.get(obligation.source_id)
    ext_source_version = (
        ext_source.version_id or ext_source.version
        if ext_source is not None
        else obligation.version
    )
    ext_text = (
        f"{obligation.instrument} {obligation.provision}. "
        f"{obligation.title}. {obligation.concise_obligation_summary} "
        f"{obligation.control_objective or ''}"
    )
    ext_amounts = _extract_currency_and_amounts(ext_text)
    ext_currency = ext_amounts[0][0] if ext_amounts else ("AUD" if obligation.jurisdiction == "AU" else None)
    ext_threshold = ext_amounts[0][1] if ext_amounts else None
    ext_operator = _detect_threshold_operator(ext_text) if ext_threshold is not None else None
    ext_timing = _detect_external_timing(obligation)
    ext_actor = _detect_external_actor(ext_text)
    ext_scopes = _detect_operational_scopes(ext_text)

    # Control and facet overlap analysis
    clause_expanded_controls = _expand_control_ids(m.control_id for m in non_rejected_mappings)
    approved_expanded_controls = _expand_control_ids(m.control_id for m in approved_mappings)
    ob_controls = _expand_control_ids([obligation.control_id] if obligation.control_id else [])
    shared_controls = sorted(clause_expanded_controls & ob_controls)

    clause_facets: Set[str] = set(clause.control_facets or [])
    for m in approved_mappings:
        if obligation.control_id in _expand_control_ids([m.control_id]):
            clause_facets.update(m.mapped_facets or [])
    # Also include proposed mapping facets for candidate comparison, but track approval status separately
    candidate_facets: Set[str] = set(clause_facets)
    for m in proposed_mappings:
        if obligation.control_id in _expand_control_ids([m.control_id]):
            candidate_facets.update(m.mapped_facets or [])

    ob_facets = set(obligation.coverage_facets or [])
    shared_facets = sorted(candidate_facets & ob_facets)
    enterprise_only_facets = sorted(candidate_facets - ob_facets)
    external_unaddressed_facets = sorted(ob_facets - candidate_facets)

    # Check whether the linking control mapping is approved vs only proposed
    has_approved_control_link = bool(approved_expanded_controls & ob_controls)
    has_only_proposed_control_link = bool(shared_controls) and not has_approved_control_link
    if has_only_proposed_control_link:
        uncertainties.append(
            f"Control mapping linking clause '{clause.clause_id}' to '{obligation.control_id}' is in 'proposed' status and has not been human-approved."
        )

    if clause.review_status not in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}:
        uncertainties.append(
            f"Enterprise clause '{clause.clause_id}' has review_status='{clause.review_status.value}' and is not yet approved."
        )

    # Authority & Modality comparison
    ext_auth_str = (
        obligation.legal_authority_classification.value
        if hasattr(obligation.legal_authority_classification, "value")
        else str(obligation.legal_authority_classification or obligation.authority.value)
    )
    if ext_auth_str == "voluntary_framework" or obligation.authority.value == "voluntary":
        authority_comp = f"external_voluntary_framework_vs_{clause.authority_level.value}"
        modality_comp = (
            "enterprise_mandatory_vs_voluntary"
            if clause.mandatory
            else "aligned"
        )
    elif ext_auth_str == "regulatory_guidance_and_expectation" or obligation.authority.value == "guidance":
        authority_comp = f"external_regulatory_guidance_vs_{clause.authority_level.value}"
        modality_comp = (
            "enterprise_discretionary_vs_mandatory"
            if not clause.mandatory
            else "aligned"
        )
    else:
        authority_comp = f"external_binding_obligation_vs_{clause.authority_level.value}"
        modality_comp = (
            "enterprise_discretionary_vs_mandatory"
            if not clause.mandatory
            else "aligned"
        )

    # Scope comparison
    if ent_scopes and ext_scopes:
        if set(ent_scopes) & set(ext_scopes):
            scope_match = "aligned" if set(ent_scopes) == set(ext_scopes) else "narrower"
        else:
            scope_match = "mismatch"
    elif ent_scopes and not ext_scopes:
        # E.g. Enterprise clause is specifically about refunds, while external obligation is about credit/privacy/etc.
        if "refunds" in ent_scopes and any(
            tok in obligation.obligation_id.upper() or tok in ext_text.lower()
            for tok in ("NCCP", "CREDIT", "LENDING", "APP3", "APP8", "CPS234")
        ):
            scope_match = "mismatch"
        else:
            scope_match = "narrower"
    else:
        scope_match = "aligned" if shared_facets else "unknown"

    # Timing comparison
    timing_comp = "not_applicable"
    if ent_timing or ext_timing:
        if ent_timing == "post_execution" and ext_timing == "pre_execution":
            timing_comp = "weaker_post_execution"
        elif ent_timing == "pre_execution" and ext_timing == "post_execution":
            timing_comp = "stricter_pre_execution"
        elif ent_timing == "pre_execution" and ext_timing is None:
            timing_comp = "stricter_pre_execution"
        elif ent_timing and ext_timing and ent_timing == ext_timing:
            timing_comp = "aligned"
        else:
            timing_comp = "specified"

    # Actor comparison
    actor_comp = "not_applicable"
    if ent_actor or ext_actor:
        if ent_actor == "dual_approval" and ext_actor != "dual_approval":
            actor_comp = "stricter_actor"
        elif ent_actor and ext_actor:
            if ent_actor == ext_actor:
                actor_comp = "aligned"
            else:
                actor_comp = "different_actor"
                uncertainties.append(
                    f"Approval actor difference: enterprise specifies '{ent_actor}' whereas external obligation references '{ext_actor}'."
                )
        elif ent_actor and not ext_actor:
            actor_comp = "enterprise_specified"

    # Condition & Exception status
    condition_status = "conditional_enterprise" if clause.is_conditional else "unconditional"
    if clause.is_conditional:
        uncertainties.append(
            f"Enterprise clause is conditional ('{clause.condition_description or 'conditional trigger'}') whereas external obligation applies unconditionally within its statutory scope."
        )
    exception_status = "enterprise_exception_weakens" if clause.has_exception_clause else "no_exceptions"
    if clause.has_exception_clause:
        uncertainties.append(
            f"Enterprise clause contains an exception/waiver carve-out ('{clause.exception_description or 'exception clause'}') that may weaken coverage."
        )

    # Threshold & Currency comparison
    threshold_comp = "not_applicable"
    if ent_threshold is not None or ext_threshold is not None:
        if ent_currency and ext_currency and ent_currency.upper() != ext_currency.upper():
            threshold_comp = "currency_mismatch"
            uncertainties.append(
                f"Currency mismatch between enterprise requirement ({ent_currency} {ent_threshold:g}) "
                f"and external requirement ({ext_currency}"
                + (f" {ext_threshold:g}" if ext_threshold is not None else "")
                + "); cross-currency equivalence cannot be deterministically assumed."
            )
        elif ent_currency and ent_currency.upper() != "AUD" and obligation.jurisdiction == "AU":
            threshold_comp = "currency_mismatch"
            uncertainties.append(
                f"Currency mismatch: enterprise clause specifies non-AUD currency ({ent_currency} {ent_threshold:g}) against Australian obligation '{obligation.obligation_id}'."
            )
        elif ent_threshold is not None and ext_threshold is not None:
            e_op = ent_operator or ">"
            x_op = ext_operator or ">"
            if abs(ent_threshold - ext_threshold) < 1e-9:
                if e_op != x_op:
                    threshold_comp = "operator_boundary_difference"
                    uncertainties.append(
                        f"Threshold operator mismatch at {ent_currency or 'AUD'} {ent_threshold:g}: "
                        f"enterprise uses '{e_op}' whereas external requirement uses '{x_op}'."
                    )
                else:
                    threshold_comp = "identical"
            elif e_op in {">", ">="} and x_op in {">", ">="}:
                # For approval triggers ("transactions above X require human approval"):
                # A lower monetary trigger (AUD 500 vs AUD 1,000) captures MORE transactions -> STRICTER.
                # A higher monetary trigger (AUD 5,000 vs AUD 1,000) captures FEWER transactions -> WEAKER.
                if ent_threshold < ext_threshold:
                    threshold_comp = "stricter_enterprise"
                else:
                    threshold_comp = "weaker_enterprise"
            elif e_op in {"<", "<="} and x_op in {"<", "<="}:
                # For upper caps ("auto-execution permitted only below X"):
                if ent_threshold < ext_threshold:
                    threshold_comp = "stricter_enterprise"
                else:
                    threshold_comp = "weaker_enterprise"
        elif ent_threshold is not None and ext_threshold is None:
            threshold_comp = "enterprise_threshold_on_general_obligation"

    # Timeframe SLA comparison (e.g., 24 hours vs 72 hours, or 14 days vs 72 hours)
    ent_hours = _extract_timeframe_hours(clause.text)
    ext_hours = _extract_timeframe_hours(ext_text)
    timeframe_conflict = False
    timeframe_stricter = False
    if ent_hours is not None and ext_hours is not None:
        # Check if this is a notification/response deadline ("within X hours/days")
        if any(
            w in (clause.text or "").lower()
            for w in ("notifi", "notify", "notification", "report", "respond", "response", "escalat", "assess")
        ):
            if ent_hours > ext_hours:
                timeframe_conflict = True
                uncertainties.append(
                    f"Enterprise timeframe ({ent_hours:g} hours) exceeds external obligation deadline ({ext_hours:g} hours)."
                )
            elif ent_hours < ext_hours:
                timeframe_stricter = True

    dim = ReconciliationDimensionComparison(
        scope_match=scope_match,
        enterprise_scope=",".join(ent_scopes) if ent_scopes else "enterprise_general",
        external_scope=",".join(ext_scopes) if ext_scopes else obligation.assessment_scope,
        subject_match="aligned" if shared_facets else "partial",
        actor_comparison=actor_comp,
        enterprise_actor=ent_actor,
        external_actor=ext_actor,
        action_polarity=polarity,
        modality_comparison=modality_comp,
        threshold_comparison=threshold_comp,
        enterprise_threshold=ent_threshold,
        enterprise_operator=ent_operator,
        enterprise_currency=ent_currency,
        external_threshold=ext_threshold,
        external_operator=ext_operator,
        external_currency=ext_currency,
        timing_comparison=timing_comp,
        enterprise_timing=ent_timing,
        external_timing=ext_timing,
        condition_status=condition_status,
        exception_status=exception_status,
        authority_comparison=authority_comp,
        shared_control_ids=shared_controls,
        shared_facets=shared_facets,
        enterprise_only_facets=enterprise_only_facets,
        external_unaddressed_facets=external_unaddressed_facets,
    )

    # ── Decision Tree for Stage B Validated Relationship ──
    proposed_rel = (
        ReconciliationRelationship.PARTIALLY_OVERLAPPING
        if (shared_controls or shared_facets)
        else ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
    )

    # 1. Clause not approved or ambiguous language or currency mismatch -> UNDETERMINED
    if clause.review_status not in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}:
        validated_rel = ReconciliationRelationship.UNDETERMINED
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        rationale = (
            f"Enterprise clause '{clause.clause_id}' has review_status='{clause.review_status.value}' "
            "and must be approved before a reliable reconciliation relationship can be established."
        )
    elif _is_ambiguous_clause(clause):
        uncertainties.append(
            "Enterprise clause uses vague or indeterminate phrasing that prevents deterministic validation."
        )
        validated_rel = ReconciliationRelationship.UNDETERMINED
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        rationale = (
            f"Enterprise clause '{clause.clause_id}' uses indeterminate phrasing and cannot be "
            f"safely reconciled against '{obligation.obligation_id}' without human legal/compliance review."
        )
    elif threshold_comp == "currency_mismatch":
        validated_rel = ReconciliationRelationship.UNDETERMINED
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        rationale = (
            f"Currency mismatch between enterprise clause '{clause.clause_id}' ({ent_currency}) "
            f"and external obligation '{obligation.obligation_id}' ({ext_currency or 'AUD'}); "
            "relationship is marked 'undetermined' pending human review."
        )
    # 2. Scope mismatch (e.g., refunds vs credit decisions)
    elif scope_match == "mismatch":
        uncertainties.append(
            f"Operational scope mismatch: enterprise clause applies to '{dim.enterprise_scope}' "
            f"whereas '{obligation.obligation_id}' applies to '{dim.external_scope}'."
        )
        validated_rel = (
            ReconciliationRelationship.PARTIALLY_OVERLAPPING
            if shared_facets
            else ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
        )
        decision_status = ReconciliationDecisionStatus.PROPOSED
        rationale = (
            f"Operational scope mismatch: enterprise clause '{clause.clause_id}' governs "
            f"'{dim.enterprise_scope}' whereas external obligation '{obligation.obligation_id}' "
            f"governs '{dim.external_scope}'. Shared control or terminology does not establish equivalence."
        )
    # 3. Direct conflict: absence of control / exemption on a required control or deadline exceeding statutory limit
    elif polarity == "absence_of_control" or timeframe_conflict:
        validated_rel = ReconciliationRelationship.POTENTIAL_CONFLICT
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        if polarity == "absence_of_control":
            rationale = (
                f"Potential conflict: enterprise clause '{clause.clause_id}' waives or states that "
                f"a control is not required ('{clause.text}'), contradicting external obligation "
                f"'{obligation.obligation_id}' ({obligation.title})."
            )
        else:
            rationale = (
                f"Potential conflict: enterprise clause '{clause.clause_id}' permits a {ent_hours:g}-hour "
                f"timeframe, which exceeds the {ext_hours:g}-hour statutory/prudential limit in "
                f"'{obligation.obligation_id}'."
            )
    # 4. Threshold operator boundary mismatch (> 500 vs >= 500)
    elif threshold_comp == "operator_boundary_difference":
        e_op = ent_operator or ">"
        x_op = ext_operator or ">"
        if (e_op == ">" and x_op == ">=") or (e_op == "<=" and x_op == "<"):
            validated_rel = ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
            rationale = (
                f"Threshold operator mismatch at boundary {ent_currency or 'AUD'} {ent_threshold:g}: "
                f"enterprise clause uses '{e_op}' whereas external requirement '{obligation.obligation_id}' "
                f"uses '{x_op}', leaving the exact boundary value unaddressed."
            )
        else:
            validated_rel = ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT
            rationale = (
                f"Threshold operator difference at boundary {ent_currency or 'AUD'} {ent_threshold:g}: "
                f"enterprise clause uses '{e_op}' whereas external requirement '{obligation.obligation_id}' "
                f"uses '{x_op}', capturing the exact boundary value more strictly."
            )
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
    # 5. Weaker enterprise requirement (higher approval trigger threshold, post-execution vs pre-execution, exceptions, discretionary language)
    elif (
        threshold_comp == "weaker_enterprise"
        or timing_comp == "weaker_post_execution"
        or exception_status == "enterprise_exception_weakens"
        or modality_comp == "enterprise_discretionary_vs_mandatory"
    ):
        validated_rel = ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        reasons: List[str] = []
        if threshold_comp == "weaker_enterprise":
            reasons.append(
                f"enterprise threshold ({ent_currency or 'AUD'} {ent_operator or '>'} {ent_threshold:g}) "
                f"is weaker/less restrictive than external threshold ({ext_currency or 'AUD'} {ext_operator or '>'} {ext_threshold:g})"
            )
        if timing_comp == "weaker_post_execution":
            reasons.append(
                "enterprise clause only requires post-execution review whereas external obligation requires pre-execution control"
            )
        if exception_status == "enterprise_exception_weakens":
            reasons.append(
                f"enterprise clause includes a weakening exception/waiver ({clause.exception_description})"
            )
        if modality_comp == "enterprise_discretionary_vs_mandatory":
            reasons.append(
                "enterprise clause uses discretionary/non-mandatory language against a mandatory external obligation"
            )
        rationale = (
            f"Enterprise clause '{clause.clause_id}' is weaker or potentially insufficient "
            f"relative to '{obligation.obligation_id}': {'; '.join(reasons)}."
        )
    # 6. Conditional enterprise requirement (narrows applicability unless explicitly stricter)
    elif clause.is_conditional:
        validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        rationale = (
            f"Enterprise clause '{clause.clause_id}' is conditional ({clause.condition_description}), "
            f"so it only partially overlaps with unconditional external obligation '{obligation.obligation_id}'."
        )
    # 7. Different approval actor (e.g. Senior Manager vs Authorised Officer / Responsible Manager / Board)
    elif actor_comp == "different_actor":
        ent_rank = ACTOR_RANK.get(ent_actor or "", 0)
        ext_rank = ACTOR_RANK.get(ext_actor or "", 0)
        if ext_rank > ent_rank > 0:
            validated_rel = ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
            rationale = (
                f"Enterprise clause '{clause.clause_id}' assigns approval to '{ent_actor}', which is "
                f"lower in governance authority than '{ext_actor}' referenced in '{obligation.obligation_id}'."
            )
        else:
            validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
            rationale = (
                f"Enterprise clause '{clause.clause_id}' specifies approval actor '{ent_actor}' "
                f"whereas '{obligation.obligation_id}' references '{ext_actor}'; cannot assume equivalence without human review."
            )
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
    # 8. Stricter enterprise requirement (lower AUD approval threshold, dual approval, stricter timeframe, total prohibition on conditional activity, or pre-execution numeric gate)
    elif (
        threshold_comp == "stricter_enterprise"
        or timeframe_stricter
        or actor_comp == "stricter_actor"
        or (
            threshold_comp == "enterprise_threshold_on_general_obligation"
            and ent_timing == "pre_execution"
            and bool(shared_facets or shared_controls)
        )
        or (
            polarity == "prohibition"
            and not external_unaddressed_facets
            and has_approved_control_link
        )
    ):
        validated_rel = ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT
        decision_status = ReconciliationDecisionStatus.PROPOSED
        stricter_reasons: List[str] = []
        if threshold_comp == "stricter_enterprise":
            stricter_reasons.append(
                f"lower monetary approval threshold ({ent_currency or 'AUD'} {ent_operator or '>'} {ent_threshold:g} vs {ext_currency or 'AUD'} {ext_operator or '>'} {ext_threshold:g})"
            )
        elif threshold_comp == "enterprise_threshold_on_general_obligation":
            stricter_reasons.append(
                f"enforces quantitative pre-execution approval threshold ({ent_currency or 'AUD'} {ent_operator or '>'} {ent_threshold:g})"
            )
        if timeframe_stricter:
            stricter_reasons.append(
                f"shorter mandatory timeframe ({ent_hours:g} hours vs {ext_hours:g} hours)"
            )
        if actor_comp == "stricter_actor":
            stricter_reasons.append("requires dual/two-up approval sign-off")
        if polarity == "prohibition":
            stricter_reasons.append("enforces a strict prohibition")
        rationale = (
            f"Enterprise clause '{clause.clause_id}' imposes stricter conditions than "
            f"'{obligation.obligation_id}': {', '.join(stricter_reasons)}."
        )
    # 9. Same Control ID but different obligations / unaddressed facets (NEVER equivalent!)
    elif external_unaddressed_facets or not shared_facets:
        validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
        decision_status = ReconciliationDecisionStatus.PROPOSED
        if not shared_facets:
            rationale = (
                f"Enterprise clause '{clause.clause_id}' shares control '{ ', '.join(shared_controls) }' "
                f"with '{obligation.obligation_id}' ({obligation.title}), but addresses none of its "
                f"specific coverage facets ({', '.join(sorted(ob_facets))}). Sharing a Control ID never establishes equivalence."
            )
        else:
            rationale = (
                f"Enterprise clause '{clause.clause_id}' addresses facets {shared_facets} of "
                f"'{obligation.obligation_id}', but leaves facets {external_unaddressed_facets} unaddressed."
            )
    # 10. All facets covered, but control mapping is only 'proposed' (not approved)
    elif has_only_proposed_control_link:
        validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
        decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
        rationale = (
            f"Enterprise clause '{clause.clause_id}' covers the facets of '{obligation.obligation_id}', "
            "but the underlying ClauseControlMapping is still in 'proposed' status and has not been human-approved."
        )
    # 11. Full facet alignment, approved clause, approved control mapping, aligned scope/actor/timing/modality, no weakening conditions/exceptions
    else:
        validated_rel = ReconciliationRelationship.EQUIVALENT
        decision_status = ReconciliationDecisionStatus.PROPOSED
        rationale = (
            f"Enterprise clause '{clause.clause_id}' covers all required facets ({shared_facets}) "
            f"of '{obligation.obligation_id}' ({obligation.title}) with aligned scope, mandatory strength, "
            "and approved control mapping. Remains in 'proposed' decision_status until approved by an authorised reviewer."
        )

    return ReconciliationDecision(
        reconciliation_id=_deterministic_reconciliation_id(
            clause.tenant_id,
            enterprise_baseline.baseline_id,
            clause.clause_id,
            obligation.obligation_id,
        ),
        tenant_id=clause.tenant_id,
        enterprise_clause_id=clause.clause_id,
        external_obligation_id=obligation.obligation_id,
        external_source_id=obligation.source_id,
        external_source_version=ext_source_version,
        external_provision=obligation.provision,
        external_legal_authority=ext_auth_str,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        enterprise_policy_id=clause.policy_id,
        enterprise_policy_name=policy_name or clause.source_name,
        enterprise_policy_version=policy_version,
        enterprise_authority_level=clause.authority_level.value,
        enterprise_clause_sha256=clause_sha,
        enterprise_baseline_id=enterprise_baseline.baseline_id,
        enterprise_baseline_version=enterprise_baseline.version,
        enterprise_baseline_revision=enterprise_baseline.revision,
        enterprise_baseline_sha256=enterprise_baseline.baseline_sha256 or "",
        stage_a_candidate_reason=stage_a_reason,
        proposed_relationship=proposed_rel,
        validated_relationship=validated_rel,
        decision_status=decision_status,
        supporting_passages=[
            clause.text,
            f"[{obligation.obligation_id} — {obligation.provision}] {obligation.concise_obligation_summary}",
        ],
        comparison_rationale=rationale,
        dimension_comparison=dim,
        uncertainties=uncertainties,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage A: Candidate Relationship Generation
# ─────────────────────────────────────────────────────────────────────────────

def _match_topic_obligations_for_unmapped_or_negative_clause(
    clause: EnterpriseClause,
    obligations: Sequence[AtomicObligation],
) -> List[Tuple[AtomicObligation, str]]:
    """Find candidate external obligations when a clause has absence-of-control or explicit citations."""
    text_lower = (clause.text or "").lower()
    scopes = set(_detect_operational_scopes(clause.text))
    matches: List[Tuple[AtomicObligation, str]] = []

    for ob in obligations:
        ob_text_lower = f"{ob.obligation_id} {ob.instrument} {ob.provision} {ob.title} {ob.concise_obligation_summary}".lower()
        # Check explicit citation or scope/keyword match
        if "app 8" in text_lower or "cross-border" in text_lower or "overseas" in text_lower:
            if ob.obligation_id == "AU-PRIV-APP8-CROSSBORDER":
                matches.append((ob, "Topic/citation match on cross-border disclosure (APP 8)."))
                continue
        if "privacy impact assessment" in text_lower or "pia" in text_lower.split():
            if ob.obligation_id in {"AU-PRIV-APP1-GOV", "AU-OAIC-APPG-CH1-PIA"}:
                matches.append((ob, "Topic match on Privacy Impact Assessment / APP 1 governance."))
                continue
        if ("72 hour" in text_lower or "72-hour" in text_lower or "apra notification" in text_lower or "security incident" in text_lower):
            if ob.obligation_id == "AU-APRA-CPS234-INCIDENT":
                matches.append((ob, "Topic/citation match on CPS 234 security incident notification."))
                continue
        if ("human approval" in text_lower or "human oversight" in text_lower or "override" in text_lower or "refund" in text_lower):
            if ob.control_id == "CTRL-HUMAN-OVERSIGHT" or ob.obligation_id == "AU-NAIC-AI6-TEST-HUMAN":
                matches.append((ob, "Topic match on human oversight and approval gate."))
                continue
        if "credit" in scopes or "credit_decisions" in scopes:
            if ob.obligation_id == "AU-NCCP-S128-131-LENDING":
                matches.append((ob, "Topic match on consumer credit suitability (NCCP Act)."))
                continue
        if "complaints_idr" in scopes and ob.source_id == "ASIC-RG271":
            matches.append((ob, "Topic match on internal dispute resolution (ASIC RG 271)."))
            continue
        # Check facet keyword overlap if clause has absence_of_control
        if ABSENCE_OF_CONTROL_PATTERN.search(clause.text or ""):
            for facet, keywords in (ob.facet_keywords or {}).items():
                if any(kw.lower() in text_lower for kw in keywords):
                    matches.append((ob, f"Negative/exemption clause matches facet keyword for '{facet}'."))
                    break
    return matches


def _detect_internal_enterprise_conflicts(
    clauses: Sequence[EnterpriseClause],
    enterprise_baseline: EnterpriseBaseline,
    regulatory_pack: RegulatoryPack,
    policy_versions: Dict[str, str],
) -> List[ReconciliationDecision]:
    """Detect conflicts between two approved enterprise clauses within the same baseline."""
    decisions: List[ReconciliationDecision] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    for i, c1 in enumerate(clauses):
        for c2 in clauses[i + 1 :]:
            if c1.clause_id == c2.clause_id:
                continue
            pair_key = tuple(sorted((c1.clause_id, c2.clause_id)))
            if pair_key in seen_pairs:
                continue

            c1_controls = _expand_control_ids(
                m.control_id
                for m in (c1.control_mappings or [])
                if m.review_status != ClauseReviewStatus.REJECTED
            )
            c2_controls = _expand_control_ids(
                m.control_id
                for m in (c2.control_mappings or [])
                if m.review_status != ClauseReviewStatus.REJECTED
            )
            shared_controls = sorted(c1_controls & c2_controls)
            shared_facets = sorted(set(c1.control_facets or []) & set(c2.control_facets or []))

            if not shared_controls and not shared_facets:
                continue

            conflict_reasons: List[str] = []
            # 1. Conflicting monetary thresholds
            if c1.thresholds_aud and c2.thresholds_aud:
                t1, t2 = c1.thresholds_aud[0], c2.thresholds_aud[0]
                op1, op2 = c1.threshold_operator or ">", c2.threshold_operator or ">"
                if abs(t1 - t2) > 1e-9 or op1 != op2:
                    conflict_reasons.append(
                        f"Conflicting enterprise approval thresholds: '{c1.source_name}' specifies "
                        f"AUD {op1} {t1:g} whereas '{c2.source_name}' specifies AUD {op2} {t2:g}"
                    )
            # 2. Conflicting approval timing (pre_execution vs post_execution)
            t_time1 = c1.approval_timing or _detect_approval_timing(c1.text)
            t_time2 = c2.approval_timing or _detect_approval_timing(c2.text)
            if t_time1 and t_time2 and t_time1 != t_time2:
                conflict_reasons.append(
                    f"Conflicting approval timing: '{c1.source_name}' specifies '{t_time1}' "
                    f"whereas '{c2.source_name}' specifies '{t_time2}'"
                )
            # 3. Conflicting polarity (positive/prohibition vs absence_of_control)
            pol1 = _detect_action_polarity(c1)
            pol2 = _detect_action_polarity(c2)
            if {pol1, pol2} == {"absence_of_control", "positive_requirement"} or {
                pol1,
                pol2,
            } == {"absence_of_control", "prohibition"}:
                conflict_reasons.append(
                    f"Conflicting requirement polarity between '{c1.source_name}' ({pol1}) "
                    f"and '{c2.source_name}' ({pol2})"
                )

            if not conflict_reasons:
                continue

            seen_pairs.add(pair_key)
            dim = ReconciliationDimensionComparison(
                scope_match="internal_enterprise_comparison",
                enterprise_scope=c1.source_name,
                external_scope=c2.source_name,
                subject_match="aligned",
                actor_comparison="internal_comparison",
                enterprise_actor=c1.required_approval_role,
                external_actor=c2.required_approval_role,
                action_polarity=f"{pol1}_vs_{pol2}",
                modality_comparison="internal_enterprise_conflict",
                threshold_comparison="internal_threshold_conflict"
                if (c1.thresholds_aud and c2.thresholds_aud)
                else "not_applicable",
                enterprise_threshold=c1.thresholds_aud[0] if c1.thresholds_aud else None,
                enterprise_operator=c1.threshold_operator,
                enterprise_currency=c1.threshold_currency or "AUD",
                external_threshold=c2.thresholds_aud[0] if c2.thresholds_aud else None,
                external_operator=c2.threshold_operator,
                external_currency=c2.threshold_currency or "AUD",
                timing_comparison=f"{t_time1}_vs_{t_time2}" if (t_time1 or t_time2) else "not_applicable",
                enterprise_timing=t_time1,
                external_timing=t_time2,
                authority_comparison=f"{c1.authority_level.value}_vs_{c2.authority_level.value}",
                shared_control_ids=shared_controls,
                shared_facets=shared_facets,
            )
            decisions.append(
                ReconciliationDecision(
                    reconciliation_id=_deterministic_reconciliation_id(
                        c1.tenant_id,
                        enterprise_baseline.baseline_id,
                        c1.clause_id,
                        None,
                        peer_enterprise_clause_id=c2.clause_id,
                    ),
                    tenant_id=c1.tenant_id,
                    enterprise_clause_id=c1.clause_id,
                    external_obligation_id=None,
                    peer_enterprise_clause_id=c2.clause_id,
                    regulatory_pack_id=regulatory_pack.pack_id,
                    regulatory_pack_version=regulatory_pack.version,
                    enterprise_policy_id=c1.policy_id,
                    enterprise_policy_name=c1.source_name,
                    enterprise_policy_version=policy_versions.get(c1.policy_id, "1.0.0"),
                    enterprise_authority_level=c1.authority_level.value,
                    enterprise_clause_sha256=compute_clause_sha256(c1),
                    enterprise_baseline_id=enterprise_baseline.baseline_id,
                    enterprise_baseline_version=enterprise_baseline.version,
                    enterprise_baseline_revision=enterprise_baseline.revision,
                    enterprise_baseline_sha256=enterprise_baseline.baseline_sha256 or "",
                    stage_a_candidate_reason=(
                        f"Internal enterprise baseline comparison on shared controls {shared_controls} / facets {shared_facets}."
                    ),
                    proposed_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
                    validated_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
                    decision_status=ReconciliationDecisionStatus.NEEDS_REVIEW,
                    supporting_passages=[
                        f"[{c1.source_name} / {c1.clause_id}] {c1.text}",
                        f"[{c2.source_name} / {c2.clause_id}] {c2.text}",
                    ],
                    comparison_rationale="; ".join(conflict_reasons) + ".",
                    dimension_comparison=dim,
                    uncertainties=conflict_reasons,
                )
            )

    return decisions


def generate_reconciliation_candidates(
    *,
    tenant_id: str,
    enterprise_baseline: EnterpriseBaseline,
    regulatory_pack: Optional[RegulatoryPack] = None,
    policies: Optional[Sequence[EnterprisePolicy]] = None,
    control_library: Optional[UnifiedControlLibrary] = None,
    obligation_mappings: Optional[ObligationControlMappingCatalogue] = None,
    use_case: Optional[BankingUseCase] = None,
    include_non_applicable: bool = False,
    include_proposed_clauses: bool = False,
) -> List[ReconciliationDecision]:
    """Execute Stage A (Candidate Generation) followed by Stage B (Relationship Validation)
    across an EnterpriseBaseline.

    Returns deterministic ReconciliationDecision records in 'proposed' or 'needs_review'
    status. Never auto-approves any reconciliation decision.
    """
    if enterprise_baseline.tenant_id != tenant_id:
        raise ValueError("Tenant mismatch when generating reconciliation candidates.")

    reg_pack = regulatory_pack or load_regulatory_pack()
    ctrl_lib = control_library or load_unified_control_library()
    ob_map_cat = obligation_mappings or load_obligation_control_mappings()

    # Determine applicable external obligations if use_case is provided
    applicable_ob_ids: Optional[Set[str]] = None
    if use_case is not None and not include_non_applicable:
        app_decisions = select_applicable_obligations(reg_pack.obligations, use_case)
        applicable_ob_ids = {
            d.obligation_id
            for d in app_decisions
            if d.status
            in {
                ApplicabilityStatus.APPLICABLE,
                ApplicabilityStatus.CONDITIONAL,
                ApplicabilityStatus.UNDETERMINED,
            }
        }

    candidate_obligations = [
        ob
        for ob in reg_pack.obligations
        if applicable_ob_ids is None or ob.obligation_id in applicable_ob_ids
    ]

    # Build lookup from canonical control_id -> list of AtomicObligation
    control_to_obligations: Dict[str, List[AtomicObligation]] = {}
    ob_by_id = {ob.obligation_id: ob for ob in candidate_obligations}

    for ob in candidate_obligations:
        if ob.control_id:
            control_to_obligations.setdefault(ob.control_id, []).append(ob)

    for ctrl in ctrl_lib.controls:
        for oid in ctrl.associated_obligation_ids:
            if oid in ob_by_id:
                existing = control_to_obligations.setdefault(ctrl.control_id, [])
                if all(x.obligation_id != oid for x in existing):
                    existing.append(ob_by_id[oid])

    for m in ob_map_cat.mappings:
        if m.obligation_id in ob_by_id:
            existing = control_to_obligations.setdefault(m.control_id, [])
            if all(x.obligation_id != m.obligation_id for x in existing):
                existing.append(ob_by_id[m.obligation_id])

    # Resolve clauses and policy versions
    policy_versions: Dict[str, str] = dict(enterprise_baseline.source_policy_versions or {})
    policy_names: Dict[str, str] = {}
    superseded_policy_ids: Set[str] = set()
    if policies:
        for p in policies:
            policy_versions[p.policy_id] = p.version
            policy_names[p.policy_id] = p.name
            if p.status in {"superseded", "retired"}:
                superseded_policy_ids.add(p.policy_id)

    raw_clauses: List[EnterpriseClause] = []
    if enterprise_baseline.clause_snapshots:
        raw_clauses = list(enterprise_baseline.clause_snapshots)
    elif policies:
        for p in policies:
            raw_clauses.extend(p.clauses)

    # Filter clauses by review status and policy status
    active_clauses: List[EnterpriseClause] = []
    for clause in raw_clauses:
        if clause.policy_id in superseded_policy_ids:
            continue
        if clause.review_status == ClauseReviewStatus.REJECTED:
            continue
        if (
            not include_proposed_clauses
            and clause.review_status
            not in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
        ):
            continue
        active_clauses.append(clause)

    decisions: List[ReconciliationDecision] = []

    for clause in active_clauses:
        pol_version = policy_versions.get(clause.policy_id, enterprise_baseline.version)
        pol_name = policy_names.get(clause.policy_id, clause.source_name)

        # Stage A: Gather candidate (obligation, reason) pairs
        matched_obligations: Dict[str, Tuple[AtomicObligation, List[str]]] = {}

        # Signal 1: Non-rejected ClauseControlMappings
        non_rejected_mappings = [
            m
            for m in (clause.control_mappings or [])
            if m.review_status != ClauseReviewStatus.REJECTED
        ]
        for m in non_rejected_mappings:
            for expanded_cid in _expand_control_ids([m.control_id]):
                for ob in control_to_obligations.get(expanded_cid, []):
                    entry = matched_obligations.setdefault(ob.obligation_id, (ob, []))
                    reason = f"Control mapping '{m.control_id}' ({m.review_status.value})"
                    if expanded_cid != m.control_id:
                        reason += f" via canonical control '{expanded_cid}'"
                    if reason not in entry[1]:
                        entry[1].append(reason)

        # Signal 2: Direct coverage facet overlap
        clause_facets = set(clause.control_facets or [])
        if clause_facets:
            for ob in candidate_obligations:
                overlap = sorted(clause_facets & set(ob.coverage_facets or []))
                if overlap:
                    entry = matched_obligations.setdefault(ob.obligation_id, (ob, []))
                    reason = f"Shared coverage facets {overlap}"
                    if reason not in entry[1]:
                        entry[1].append(reason)

        # Signal 3: Topic / citation / negative-obligation match
        for ob, topic_reason in _match_topic_obligations_for_unmapped_or_negative_clause(
            clause, candidate_obligations
        ):
            entry = matched_obligations.setdefault(ob.obligation_id, (ob, []))
            if topic_reason not in entry[1]:
                entry[1].append(topic_reason)

        # If no external obligations matched, validate as standalone (additional or unmapped)
        if not matched_obligations:
            decisions.append(
                validate_candidate_relationship(
                    clause=clause,
                    obligation=None,
                    regulatory_pack=reg_pack,
                    enterprise_baseline=enterprise_baseline,
                    policy_version=pol_version,
                    policy_name=pol_name,
                    stage_a_reason="No external obligation matched via control mappings, facets, or citations.",
                )
            )
            continue

        # Also check if the clause has an explicit enterprise-only control mapping
        # (e.g., CTRL-FIN-APPROVAL-THRESHOLDS) that adds an enterprise-specific requirement
        has_enterprise_only_control = any(
            m.control_id in ENTERPRISE_ONLY_CONTROL_IDS for m in non_rejected_mappings
        )
        if has_enterprise_only_control and any(
            f in (clause.control_facets or [])
            for f in ("approval_threshold_defined", " approval_logs_retained", "dual_approval_required")
        ):
            # In addition to reconciling against human-oversight obligations, record its
            # enterprise-specific threshold nature if no human-oversight obligation matched
            pass

        for oid in sorted(matched_obligations.keys()):
            ob, reasons = matched_obligations[oid]
            decisions.append(
                validate_candidate_relationship(
                    clause=clause,
                    obligation=ob,
                    regulatory_pack=reg_pack,
                    enterprise_baseline=enterprise_baseline,
                    policy_version=pol_version,
                    policy_name=pol_name,
                    stage_a_reason="; ".join(reasons),
                )
            )

    # Signal 4: Internal enterprise-to-enterprise clause conflicts
    internal_conflicts = _detect_internal_enterprise_conflicts(
        active_clauses,
        enterprise_baseline=enterprise_baseline,
        regulatory_pack=reg_pack,
        policy_versions=policy_versions,
    )
    decisions.extend(internal_conflicts)

    return decisions


# ─────────────────────────────────────────────────────────────────────────────
# Staleness Detection & Human Review Service
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_reconciliation_staleness(
    decision: ReconciliationDecision,
    *,
    enterprise_baseline: Optional[EnterpriseBaseline] = None,
    regulatory_pack: Optional[RegulatoryPack] = None,
    policies: Optional[Sequence[EnterprisePolicy]] = None,
) -> ReconciliationDecision:
    """Check whether a ReconciliationDecision has become stale due to version or content changes."""
    stale_reasons: List[str] = []

    if regulatory_pack is not None:
        if decision.regulatory_pack_id != regulatory_pack.pack_id:
            stale_reasons.append(
                f"Regulatory pack ID changed from '{decision.regulatory_pack_id}' to '{regulatory_pack.pack_id}'."
            )
        elif decision.regulatory_pack_version != regulatory_pack.version:
            stale_reasons.append(
                f"External regulatory pack version changed from '{decision.regulatory_pack_version}' to '{regulatory_pack.version}'."
            )
        if decision.external_obligation_id:
            ob_map = {ob.obligation_id: ob for ob in regulatory_pack.obligations}
            ext_ob = ob_map.get(decision.external_obligation_id)
            if ext_ob is None:
                stale_reasons.append(
                    f"Referenced external obligation '{decision.external_obligation_id}' is no longer present in regulatory pack '{regulatory_pack.version}'."
                )
            else:
                src_map = {s.source_id: s for s in regulatory_pack.sources}
                src = src_map.get(ext_ob.source_id)
                current_src_ver = (
                    (src.version_id or src.version) if src is not None else ext_ob.version
                )
                if (
                    decision.external_source_version
                    and current_src_ver
                    and decision.external_source_version != current_src_ver
                ):
                    stale_reasons.append(
                        f"External source '{ext_ob.source_id}' version changed from '{decision.external_source_version}' to '{current_src_ver}'."
                    )

    if policies:
        for pol in policies:
            if pol.policy_id == decision.enterprise_policy_id:
                if pol.status in {"superseded", "retired"}:
                    stale_reasons.append(
                        f"Enterprise policy '{pol.name}' ({pol.policy_id}) has status='{pol.status}'."
                    )
                if pol.version != decision.enterprise_policy_version:
                    stale_reasons.append(
                        f"Enterprise policy version changed from '{decision.enterprise_policy_version}' to '{pol.version}'."
                    )

    if enterprise_baseline is not None:
        if (
            decision.enterprise_baseline_id == enterprise_baseline.baseline_id
            and enterprise_baseline.baseline_sha256
            and decision.enterprise_baseline_sha256
            and decision.enterprise_baseline_sha256 != enterprise_baseline.baseline_sha256
        ):
            stale_reasons.append(
                "Enterprise baseline cryptographic fingerprint changed since reconciliation."
            )
        elif (
            decision.enterprise_baseline_id == enterprise_baseline.baseline_id
            and decision.enterprise_baseline_version != enterprise_baseline.version
        ):
            stale_reasons.append(
                f"Enterprise baseline version changed from '{decision.enterprise_baseline_version}' to '{enterprise_baseline.version}'."
            )

        if enterprise_baseline.clause_snapshots:
            clause_map = {c.clause_id: c for c in enterprise_baseline.clause_snapshots}
            clause = clause_map.get(decision.enterprise_clause_id)
            if clause is None:
                stale_reasons.append(
                    f"Enterprise clause '{decision.enterprise_clause_id}' is no longer present in the enterprise baseline."
                )
            else:
                if clause.review_status not in {
                    ClauseReviewStatus.APPROVED,
                    ClauseReviewStatus.CONFIRMED,
                }:
                    stale_reasons.append(
                        f"Enterprise clause '{clause.clause_id}' review_status changed to '{clause.review_status.value}'."
                    )
                current_sha = compute_clause_sha256(clause)
                if (
                    decision.enterprise_clause_sha256
                    and decision.enterprise_clause_sha256 != current_sha
                ):
                    stale_reasons.append(
                        f"Enterprise clause '{clause.clause_id}' text, metadata, or control mappings changed since reconciliation."
                    )

    if stale_reasons:
        return decision.model_copy(
            update={
                "is_stale": True,
                "stale_reason": " ".join(stale_reasons),
            }
        )
    return decision


AUTHORISED_RECONCILIATION_REVIEWER_ROLES: Set[str] = {
    "reviewer",
    "legal",
    "compliance",
    "risk",
    "admin",
}


def review_reconciliation_decision(
    decision: ReconciliationDecision,
    *,
    decision_status: ReconciliationDecisionStatus,
    actor: str,
    role: str,
    approved_relationship: Optional[ReconciliationRelationship] = None,
    comment: Optional[str] = None,
    expected_revision: Optional[int] = None,
) -> ReconciliationDecision:
    """Apply an authorised human review decision to a ReconciliationDecision."""
    normalised_role = (role or "").strip().lower()
    if normalised_role not in AUTHORISED_RECONCILIATION_REVIEWER_ROLES:
        raise PermissionError(
            f"Role '{role}' is not authorised to approve or review requirement reconciliations. "
            "Required role: reviewer, legal, compliance, risk, or admin."
        )
    if not (actor or "").strip():
        raise PermissionError("Reviewer actor identity is required.")

    if expected_revision is not None and expected_revision != decision.revision:
        raise ValueError(
            f"Stale revision: expected {expected_revision}, current revision is {decision.revision}."
        )

    if decision.is_stale and decision_status == ReconciliationDecisionStatus.APPROVED:
        raise ValueError(
            f"Cannot approve a stale reconciliation decision ({decision.stale_reason}). "
            "Re-run reconciliation against the current baseline and regulatory pack first."
        )

    effective_rel = approved_relationship or decision.validated_relationship
    if decision_status == ReconciliationDecisionStatus.APPROVED:
        if effective_rel == ReconciliationRelationship.UNDETERMINED:
            raise ValueError(
                "Cannot approve a reconciliation with relationship 'undetermined'. "
                "Specify the resolved ReconciliationRelationship and rationale."
            )
        if (
            approved_relationship is not None
            and approved_relationship != decision.validated_relationship
            and not (comment and comment.strip())
        ):
            raise ValueError(
                "Overriding the Stage B validated relationship requires a non-empty review comment explaining the rationale."
            )

    now = datetime.now(timezone.utc)
    new_revision = decision.revision + 1
    audit_entry = ReconciliationAuditEntry(
        timestamp=now,
        actor=actor.strip(),
        role=normalised_role,
        previous_status=decision.decision_status.value,
        new_status=decision_status.value,
        previous_relationship=(
            decision.approved_relationship.value
            if decision.approved_relationship
            else decision.validated_relationship.value
        ),
        new_relationship=effective_rel.value,
        comment=comment.strip() if comment else None,
        revision=new_revision,
    )

    updated_history = list(decision.audit_history or [])
    updated_history.append(audit_entry)

    return decision.model_copy(
        update={
            "decision_status": decision_status,
            "approved_relationship": (
                effective_rel
                if decision_status == ReconciliationDecisionStatus.APPROVED
                else None
            ),
            "validated_relationship": effective_rel,
            "reviewer_id": actor.strip(),
            "reviewer_role": normalised_role,
            "reviewed_at": now,
            "review_comment": comment.strip() if comment else decision.review_comment,
            "revision": new_revision,
            "audit_history": updated_history,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Effective Assessment Baseline Composition Service (Section 6)
# ─────────────────────────────────────────────────────────────────────────────

def compose_effective_assessment_baseline(
    *,
    tenant_id: str,
    regulatory_pack: Optional[RegulatoryPack] = None,
    use_case: Optional[BankingUseCase] = None,
    enterprise_baseline: Optional[EnterpriseBaseline] = None,
    reconciliation_decisions: Sequence[ReconciliationDecision] = (),
    policies: Optional[Sequence[EnterprisePolicy]] = None,
    as_of_date: Optional[str] = None,
) -> EffectiveAssessmentBaseline:
    """Deterministically compose an Effective Assessment Baseline.

    Preserves:
    1. Every independently applicable external obligation from the Shared Regulatory Library.
    2. Additional approved enterprise requirements.
    3. Stricter enterprise conditions (thresholds, operators, timing, actors).
    4. Unmapped approved enterprise requirements.
    5. Unresolved conflicts and uncertain relationships.
    6. Original source and version references.
    7. Reviewed equivalence presentation groups without removing binding obligations.
    """
    reg_pack = regulatory_pack or load_regulatory_pack()
    uc = use_case or BankingUseCase.enterprise_baseline()
    effective_date_str = str(as_of_date or reg_pack.verified_as_of or "2026-11-02")

    if enterprise_baseline is not None:
        if enterprise_baseline.tenant_id != tenant_id:
            raise ValueError("Enterprise baseline does not belong to this tenant.")
        if not verify_baseline_integrity(enterprise_baseline):
            raise ValueError(
                "Enterprise baseline cryptographic fingerprint verification failed."
            )

    source_lookup = {s.source_id: s for s in reg_pack.sources}
    app_decisions = select_applicable_obligations(reg_pack.obligations, uc)
    app_by_id = {d.obligation_id: d for d in app_decisions}

    applicable_obligations: List[AtomicObligation] = []
    non_applicable_ids: List[str] = []
    human_confirm_ids: List[str] = []

    for ob in reg_pack.obligations:
        d = app_by_id.get(ob.obligation_id)
        if d is None or d.status == ApplicabilityStatus.NOT_APPLICABLE:
            non_applicable_ids.append(ob.obligation_id)
            continue
        if d.status in {ApplicabilityStatus.CONDITIONAL, ApplicabilityStatus.UNDETERMINED}:
            human_confirm_ids.append(ob.obligation_id)
        applicable_obligations.append(ob)

    applicable_external_ids = [ob.obligation_id for ob in applicable_obligations]

    # Step 1: Seed every applicable external obligation into requirements
    ext_items_by_ob_id: Dict[str, EffectiveBaselineRequirementItem] = {}
    for ob in applicable_obligations:
        src = source_lookup.get(ob.source_id)
        src_title = src.title if src is not None else ob.instrument
        src_version = (src.version_id or src.version) if src is not None else ob.version
        ext_auth_str = (
            ob.legal_authority_classification.value
            if hasattr(ob.legal_authority_classification, "value")
            else str(ob.legal_authority_classification or ob.authority.value)
        )
        is_binding = ext_auth_str in {
            "binding_legal_or_prudential_obligation",
            "enforceable_regulatory_requirement",
        }
        src_ref = EffectiveBaselineSourceReference(
            source_kind="shared_regulatory_library",
            source_id=ob.source_id,
            source_title=src_title,
            version=src_version,
            obligation_or_clause_id=ob.obligation_id,
            provision_or_location=ob.provision,
            authority_classification=ext_auth_str,
            effective_from=str(ob.effective_from) if ob.effective_from else None,
        )
        item = EffectiveBaselineRequirementItem(
            item_id=f"REQ-EXT-{ob.obligation_id}",
            item_kind="external_obligation",
            obligation_id=ob.obligation_id,
            title=ob.title,
            summary=ob.concise_obligation_summary or ob.title,
            authority_classification=ext_auth_str,
            is_legally_binding=is_binding,
            control_ids=[ob.control_id] if ob.control_id else [],
            required_facets=list(ob.coverage_facets or []),
            source_references=[src_ref],
        )
        ext_items_by_ob_id[ob.obligation_id] = item

    included_clause_ids: List[str] = []
    excluded_clause_ids: List[str] = []
    approved_rec_ids: List[str] = []
    stale_rec_ids: List[str] = []
    enterprise_items: List[EffectiveBaselineRequirementItem] = []
    presentation_groups: List[EffectivePresentationGroup] = []
    unresolved_items: List[EffectiveBaselineUnresolvedItem] = []
    potential_conflicts: List[EffectiveBaselineUnresolvedItem] = []
    warnings: List[str] = []

    if enterprise_baseline is not None:
        warnings.extend(enterprise_baseline.warnings or [])
        superseded_policy_ids: Set[str] = set()
        policy_versions: Dict[str, str] = dict(
            enterprise_baseline.source_policy_versions or {}
        )
        if policies:
            for p in policies:
                policy_versions[p.policy_id] = p.version
                if p.status in {"superseded", "retired"}:
                    superseded_policy_ids.add(p.policy_id)
                    warnings.append(
                        f"Enterprise policy '{p.name}' ({p.policy_id}) has status='{p.status}' and its clauses are excluded from confirmed baseline requirements."
                    )

        raw_clauses: List[EnterpriseClause] = []
        if enterprise_baseline.clause_snapshots:
            raw_clauses = list(enterprise_baseline.clause_snapshots)
        elif policies:
            for p in policies:
                raw_clauses.extend(p.clauses)

        approved_clauses_by_id: Dict[str, EnterpriseClause] = {}
        for clause in raw_clauses:
            if clause.policy_id in superseded_policy_ids:
                excluded_clause_ids.append(clause.clause_id)
                continue
            if clause.review_status in {
                ClauseReviewStatus.APPROVED,
                ClauseReviewStatus.CONFIRMED,
            }:
                approved_clauses_by_id[clause.clause_id] = clause
                included_clause_ids.append(clause.clause_id)
            else:
                excluded_clause_ids.append(clause.clause_id)
                warnings.append(
                    f"Enterprise clause '{clause.clause_id}' has review_status='{clause.review_status.value}' and is excluded from the Effective Assessment Baseline."
                )

        # Evaluate staleness on all provided reconciliation decisions
        evaluated_decisions: List[ReconciliationDecision] = [
            evaluate_reconciliation_staleness(
                d,
                enterprise_baseline=enterprise_baseline,
                regulatory_pack=reg_pack,
                policies=policies,
            )
            for d in reconciliation_decisions
            if d.tenant_id == tenant_id
            and d.enterprise_baseline_id == enterprise_baseline.baseline_id
        ]

        decisions_by_clause: Dict[str, List[ReconciliationDecision]] = {}
        for d in sorted(evaluated_decisions, key=lambda x: x.reconciliation_id):
            decisions_by_clause.setdefault(d.enterprise_clause_id, []).append(d)
            if d.is_stale:
                stale_rec_ids.append(d.reconciliation_id)
                unresolved_item = EffectiveBaselineUnresolvedItem(
                    reconciliation_id=d.reconciliation_id,
                    enterprise_clause_id=d.enterprise_clause_id,
                    external_obligation_id=d.external_obligation_id,
                    peer_enterprise_clause_id=d.peer_enterprise_clause_id,
                    validated_relationship=d.validated_relationship,
                    decision_status=d.decision_status,
                    severity="high",
                    summary=f"Stale reconciliation decision: {d.stale_reason}",
                    uncertainties=[*(d.uncertainties or []), d.stale_reason or "Stale version"],
                    requires_human_resolution=True,
                )
                unresolved_items.append(unresolved_item)
                continue

            # Exclude decisions for clauses that are not approved
            if d.enterprise_clause_id not in approved_clauses_by_id:
                continue

            clause = approved_clauses_by_id[d.enterprise_clause_id]
            pol_ver = policy_versions.get(
                clause.policy_id, d.enterprise_policy_version or enterprise_baseline.version
            )
            clause_ref = EffectiveBaselineSourceReference(
                source_kind="enterprise_internal_baseline",
                source_id=clause.policy_id,
                source_title=d.enterprise_policy_name or clause.source_name,
                version=pol_ver,
                obligation_or_clause_id=clause.clause_id,
                provision_or_location=(
                    f"Page {clause.page}" if clause.page else f"Policy {clause.source_name}"
                ),
                authority_classification=clause.authority_level.value,
            )

            rel = (
                d.approved_relationship
                if d.decision_status == ReconciliationDecisionStatus.APPROVED
                and d.approved_relationship is not None
                else d.validated_relationship
            )

            # Check if this is a conflict or weaker requirement (always surfaced in potential_conflicts)
            if rel in {
                ReconciliationRelationship.POTENTIAL_CONFLICT,
                ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
            }:
                conflict_item = EffectiveBaselineUnresolvedItem(
                    reconciliation_id=d.reconciliation_id,
                    enterprise_clause_id=d.enterprise_clause_id,
                    external_obligation_id=d.external_obligation_id,
                    peer_enterprise_clause_id=d.peer_enterprise_clause_id,
                    validated_relationship=rel,
                    decision_status=d.decision_status,
                    severity="critical"
                    if rel == ReconciliationRelationship.POTENTIAL_CONFLICT
                    else "high",
                    summary=d.comparison_rationale,
                    uncertainties=list(d.uncertainties or []),
                    requires_human_resolution=True,
                )
                potential_conflicts.append(conflict_item)
                unresolved_items.append(conflict_item)
                if d.external_obligation_id and d.external_obligation_id in ext_items_by_ob_id:
                    ext_item = ext_items_by_ob_id[d.external_obligation_id]
                    ext_item.reconciliation_ids.append(d.reconciliation_id)
                    ext_item.reconciliation_relationships.append(rel)
                    ext_item.notes.append(
                        f"Unresolved {rel.value} with enterprise clause '{clause.clause_id}': {d.comparison_rationale}"
                    )
                continue

            # If decision is not yet APPROVED by a human reviewer
            if d.decision_status != ReconciliationDecisionStatus.APPROVED:
                if d.decision_status != ReconciliationDecisionStatus.REJECTED:
                    unresolved_items.append(
                        EffectiveBaselineUnresolvedItem(
                            reconciliation_id=d.reconciliation_id,
                            enterprise_clause_id=d.enterprise_clause_id,
                            external_obligation_id=d.external_obligation_id,
                            peer_enterprise_clause_id=d.peer_enterprise_clause_id,
                            validated_relationship=rel,
                            decision_status=d.decision_status,
                            severity="high"
                            if rel == ReconciliationRelationship.UNDETERMINED
                            else "medium",
                            summary=d.comparison_rationale,
                            uncertainties=list(d.uncertainties or []),
                            requires_human_resolution=True,
                        )
                    )
                continue

            # ── Decision IS APPROVED by an authorised reviewer ──
            approved_rec_ids.append(d.reconciliation_id)

            if (
                rel == ReconciliationRelationship.EQUIVALENT
                and d.external_obligation_id
                and d.external_obligation_id in ext_items_by_ob_id
            ):
                ext_item = ext_items_by_ob_id[d.external_obligation_id]
                group_id = f"GRP-EQ-{d.external_obligation_id}-{clause.clause_id}"
                ext_item.reconciliation_ids.append(d.reconciliation_id)
                ext_item.reconciliation_relationships.append(rel)
                ext_item.presentation_group_id = group_id
                ext_item.source_references.append(clause_ref)
                ext_item.notes.append(
                    f"Reviewed equivalence established with enterprise clause '{clause.clause_id}' "
                    f"(reconciliation '{d.reconciliation_id}'). Underlying statutory and enterprise "
                    "sources remain independently traceable."
                )
                presentation_groups.append(
                    EffectivePresentationGroup(
                        group_id=group_id,
                        group_type="reviewed_equivalence_group",
                        primary_title=ext_item.title,
                        member_item_ids=[ext_item.item_id],
                        external_obligation_ids=[d.external_obligation_id],
                        enterprise_clause_ids=[clause.clause_id],
                        reconciliation_id=d.reconciliation_id,
                        source_references=list(ext_item.source_references),
                        rationale=d.comparison_rationale,
                    )
                )

            elif rel == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT:
                stricter_desc = (
                    f"[{clause.source_name} / {clause.clause_id}] {clause.text}"
                )
                ent_item_id = f"REQ-ENT-STRICT-{clause.clause_id}"
                if d.external_obligation_id and d.external_obligation_id in ext_items_by_ob_id:
                    ext_item = ext_items_by_ob_id[d.external_obligation_id]
                    ext_item.reconciliation_ids.append(d.reconciliation_id)
                    ext_item.reconciliation_relationships.append(rel)
                    ext_item.stricter_conditions.append(stricter_desc)
                    ext_item.source_references.append(clause_ref)
                    ent_item_id = f"REQ-ENT-STRICT-{clause.clause_id}-{d.external_obligation_id}"

                approved_ctrl_ids = [
                    m.control_id
                    for m in (clause.control_mappings or [])
                    if m.review_status
                    in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
                ]
                ent_item = EffectiveBaselineRequirementItem(
                    item_id=ent_item_id,
                    item_kind="stricter_enterprise_condition",
                    obligation_id=d.external_obligation_id,
                    enterprise_clause_id=clause.clause_id,
                    enterprise_policy_id=clause.policy_id,
                    title=f"Stricter Enterprise Requirement ({clause.source_name})",
                    summary=clause.text,
                    authority_classification=clause.authority_level.value,
                    is_legally_binding=False,
                    control_ids=approved_ctrl_ids,
                    required_facets=list(clause.control_facets or []),
                    stricter_conditions=[stricter_desc],
                    thresholds_aud=list(clause.thresholds_aud or []),
                    threshold_operator=clause.threshold_operator,
                    threshold_currency=clause.threshold_currency
                    or ("AUD" if clause.thresholds_aud else None),
                    approval_timing=clause.approval_timing,
                    required_approval_role=clause.required_approval_role,
                    reconciliation_ids=[d.reconciliation_id],
                    reconciliation_relationships=[rel],
                    source_references=[clause_ref],
                    notes=[d.comparison_rationale],
                )
                enterprise_items.append(ent_item)
                presentation_groups.append(
                    EffectivePresentationGroup(
                        group_id=f"GRP-STRICT-{clause.clause_id}-{d.external_obligation_id or 'ENT'}",
                        group_type="stricter_overlay_group",
                        primary_title=ent_item.title,
                        member_item_ids=[
                            *([f"REQ-EXT-{d.external_obligation_id}"] if d.external_obligation_id else []),
                            ent_item.item_id,
                        ],
                        external_obligation_ids=(
                            [d.external_obligation_id] if d.external_obligation_id else []
                        ),
                        enterprise_clause_ids=[clause.clause_id],
                        reconciliation_id=d.reconciliation_id,
                        source_references=[clause_ref],
                        rationale=d.comparison_rationale,
                    )
                )

            elif rel in {
                ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
                ReconciliationRelationship.PARTIALLY_OVERLAPPING,
            }:
                if (
                    rel == ReconciliationRelationship.PARTIALLY_OVERLAPPING
                    and d.external_obligation_id
                    and d.external_obligation_id in ext_items_by_ob_id
                ):
                    ext_item = ext_items_by_ob_id[d.external_obligation_id]
                    ext_item.reconciliation_ids.append(d.reconciliation_id)
                    ext_item.reconciliation_relationships.append(rel)
                    ext_item.notes.append(
                        f"Partial overlap with enterprise clause '{clause.clause_id}'; "
                        f"unaddressed obligation facets {d.dimension_comparison.external_unaddressed_facets} remain independently required."
                    )

                approved_ctrl_ids = [
                    m.control_id
                    for m in (clause.control_mappings or [])
                    if m.review_status
                    in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
                ]
                ent_item_id = f"REQ-ENT-ADD-{clause.clause_id}"
                if all(x.item_id != ent_item_id for x in enterprise_items):
                    ent_item = EffectiveBaselineRequirementItem(
                        item_id=ent_item_id,
                        item_kind="additional_enterprise_requirement",
                        obligation_id=d.external_obligation_id,
                        enterprise_clause_id=clause.clause_id,
                        enterprise_policy_id=clause.policy_id,
                        title=f"Enterprise Policy Requirement ({clause.source_name})",
                        summary=clause.text,
                        authority_classification=clause.authority_level.value,
                        is_legally_binding=False,
                        control_ids=approved_ctrl_ids,
                        required_facets=list(clause.control_facets or []),
                        thresholds_aud=list(clause.thresholds_aud or []),
                        threshold_operator=clause.threshold_operator,
                        threshold_currency=clause.threshold_currency
                        or ("AUD" if clause.thresholds_aud else None),
                        approval_timing=clause.approval_timing,
                        required_approval_role=clause.required_approval_role,
                        reconciliation_ids=[d.reconciliation_id],
                        reconciliation_relationships=[rel],
                        source_references=[clause_ref],
                        notes=[d.comparison_rationale],
                    )
                    enterprise_items.append(ent_item)
                    presentation_groups.append(
                        EffectivePresentationGroup(
                            group_id=f"GRP-ENT-{clause.clause_id}",
                            group_type="standalone_enterprise_clause",
                            primary_title=ent_item.title,
                            member_item_ids=[ent_item.item_id],
                            external_obligation_ids=[],
                            enterprise_clause_ids=[clause.clause_id],
                            reconciliation_id=d.reconciliation_id,
                            source_references=[clause_ref],
                            rationale=d.comparison_rationale,
                        )
                    )

            elif rel == ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP:
                ent_item_id = f"REQ-ENT-UNMAPPED-{clause.clause_id}"
                if all(x.item_id != ent_item_id for x in enterprise_items):
                    ent_item = EffectiveBaselineRequirementItem(
                        item_id=ent_item_id,
                        item_kind="unmapped_enterprise_requirement",
                        enterprise_clause_id=clause.clause_id,
                        enterprise_policy_id=clause.policy_id,
                        title=f"Unmapped Enterprise Requirement ({clause.source_name})",
                        summary=clause.text,
                        authority_classification=clause.authority_level.value,
                        is_legally_binding=False,
                        control_ids=[],
                        required_facets=list(clause.control_facets or []),
                        thresholds_aud=list(clause.thresholds_aud or []),
                        threshold_operator=clause.threshold_operator,
                        threshold_currency=clause.threshold_currency,
                        approval_timing=clause.approval_timing,
                        required_approval_role=clause.required_approval_role,
                        reconciliation_ids=[d.reconciliation_id],
                        reconciliation_relationships=[rel],
                        source_references=[clause_ref],
                        notes=[d.comparison_rationale],
                    )
                    enterprise_items.append(ent_item)

        # Ensure every approved enterprise clause in the baseline is preserved even if
        # its reconciliation is still unapproved or no reconciliation record was passed.
        represented_clause_ids: Set[str] = {
            x.enterprise_clause_id
            for x in enterprise_items
            if x.enterprise_clause_id is not None
        }
        for grp in presentation_groups:
            if grp.group_type == "reviewed_equivalence_group":
                represented_clause_ids.update(grp.enterprise_clause_ids)

        for cid, clause in sorted(approved_clauses_by_id.items()):
            if cid in represented_clause_ids:
                continue
            pol_ver = policy_versions.get(clause.policy_id, enterprise_baseline.version)
            clause_ref = EffectiveBaselineSourceReference(
                source_kind="enterprise_internal_baseline",
                source_id=clause.policy_id,
                source_title=clause.source_name,
                version=pol_ver,
                obligation_or_clause_id=clause.clause_id,
                provision_or_location=(
                    f"Page {clause.page}" if clause.page else f"Policy {clause.source_name}"
                ),
                authority_classification=clause.authority_level.value,
            )
            approved_ctrl_ids = [
                m.control_id
                for m in (clause.control_mappings or [])
                if m.review_status
                in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
            ]
            item_kind: Any = (
                "unmapped_enterprise_requirement"
                if (clause.is_unmapped or not approved_ctrl_ids)
                else "additional_enterprise_requirement"
            )
            rel_kind = (
                ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
                if item_kind == "unmapped_enterprise_requirement"
                else ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT
            )
            enterprise_items.append(
                EffectiveBaselineRequirementItem(
                    item_id=f"REQ-ENT-{cid}",
                    item_kind=item_kind,
                    enterprise_clause_id=clause.clause_id,
                    enterprise_policy_id=clause.policy_id,
                    title=f"Enterprise Policy Requirement ({clause.source_name})",
                    summary=clause.text,
                    authority_classification=clause.authority_level.value,
                    is_legally_binding=False,
                    control_ids=approved_ctrl_ids,
                    required_facets=list(clause.control_facets or []),
                    thresholds_aud=list(clause.thresholds_aud or []),
                    threshold_operator=clause.threshold_operator,
                    threshold_currency=clause.threshold_currency
                    or ("AUD" if clause.thresholds_aud else None),
                    approval_timing=clause.approval_timing,
                    required_approval_role=clause.required_approval_role,
                    reconciliation_relationships=[rel_kind],
                    source_references=[clause_ref],
                    notes=[
                        "Approved enterprise clause preserved in Effective Assessment Baseline."
                    ],
                )
            )
            if cid not in decisions_by_clause:
                unresolved_items.append(
                    EffectiveBaselineUnresolvedItem(
                        reconciliation_id=_deterministic_reconciliation_id(
                            tenant_id, enterprise_baseline.baseline_id, cid, None
                        ),
                        enterprise_clause_id=cid,
                        validated_relationship=rel_kind,
                        decision_status=ReconciliationDecisionStatus.PROPOSED,
                        severity="medium",
                        summary=f"Approved enterprise clause '{cid}' has not yet been reviewed in reconciliation.",
                        uncertainties=["Reconciliation review pending."],
                        requires_human_resolution=True,
                    )
                )

    # Combine duplicate enterprise clauses across multiple enterprise policies into
    # traceable multi-source references where texts are identical
    text_to_ent_items: Dict[str, List[EffectiveBaselineRequirementItem]] = {}
    for item in enterprise_items:
        norm = " ".join((item.summary or "").lower().split())
        text_to_ent_items.setdefault(norm, []).append(item)
    for norm_text, dup_items in text_to_ent_items.items():
        if len(dup_items) > 1:
            all_refs: List[EffectiveBaselineSourceReference] = []
            for ditem in dup_items:
                for r in ditem.source_references:
                    if r not in all_refs:
                        all_refs.append(r)
            for ditem in dup_items:
                ditem.source_references = list(all_refs)

    # Add standalone presentation groups for external obligations not already in an equivalence group
    grouped_ext_ids: Set[str] = set()
    for grp in presentation_groups:
        if grp.group_type == "reviewed_equivalence_group":
            grouped_ext_ids.update(grp.external_obligation_ids)

    for ob_id, ext_item in ext_items_by_ob_id.items():
        if ob_id not in grouped_ext_ids:
            presentation_groups.append(
                EffectivePresentationGroup(
                    group_id=f"GRP-OB-{ob_id}",
                    group_type="standalone_obligation",
                    primary_title=ext_item.title,
                    member_item_ids=[ext_item.item_id],
                    external_obligation_ids=[ob_id],
                    enterprise_clause_ids=[],
                    source_references=list(ext_item.source_references),
                    rationale="Independently applicable external obligation from the Shared Regulatory Library.",
                )
            )

    all_requirements: List[EffectiveBaselineRequirementItem] = [
        *[ext_items_by_ob_id[oid] for oid in applicable_external_ids],
        *sorted(enterprise_items, key=lambda x: x.item_id),
    ]
    presentation_groups.sort(key=lambda g: g.group_id)
    unresolved_items.sort(
        key=lambda u: (u.reconciliation_id, u.enterprise_clause_id, u.external_obligation_id or "")
    )
    potential_conflicts.sort(
        key=lambda c: (c.reconciliation_id, c.enterprise_clause_id, c.external_obligation_id or "")
    )

    applicability_summary = {
        "applicable_count": len(applicable_external_ids),
        "non_applicable_count": len(non_applicable_ids),
        "human_confirmation_required_count": len(human_confirm_ids),
        "non_applicable_obligation_ids": sorted(non_applicable_ids),
        "human_confirmation_required_obligation_ids": sorted(human_confirm_ids),
    }

    fingerprint_payload = {
        "tenant_id": tenant_id,
        "as_of_date": effective_date_str,
        "regulatory_pack_id": reg_pack.pack_id,
        "regulatory_pack_version": reg_pack.version,
        "enterprise_baseline_id": enterprise_baseline.baseline_id if enterprise_baseline else None,
        "enterprise_baseline_version": enterprise_baseline.version if enterprise_baseline else None,
        "enterprise_baseline_revision": enterprise_baseline.revision if enterprise_baseline else None,
        "enterprise_baseline_sha256": enterprise_baseline.baseline_sha256 if enterprise_baseline else None,
        "use_case": uc.model_dump(mode="json", exclude={"use_case_id"}),
        "applicable_external_obligation_ids": applicable_external_ids,
        "included_enterprise_clause_ids": sorted(included_clause_ids),
        "excluded_enterprise_clause_ids": sorted(excluded_clause_ids),
        "approved_reconciliation_ids": sorted(approved_rec_ids),
        "stale_reconciliation_ids": sorted(stale_rec_ids),
        "requirements": [r.model_dump(mode="json") for r in all_requirements],
        "presentation_groups": [g.model_dump(mode="json") for g in presentation_groups],
        "unresolved_items": [u.model_dump(mode="json") for u in unresolved_items],
        "potential_conflicts": [c.model_dump(mode="json") for c in potential_conflicts],
    }
    canonical_bytes = json.dumps(
        fingerprint_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    effective_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    effective_baseline_id = f"EBL-{effective_sha256[:16].upper()}"

    return EffectiveAssessmentBaseline(
        effective_baseline_id=effective_baseline_id,
        tenant_id=tenant_id,
        as_of_date=effective_date_str,
        regulatory_pack_id=reg_pack.pack_id,
        regulatory_pack_version=reg_pack.version,
        enterprise_baseline_id=enterprise_baseline.baseline_id if enterprise_baseline else None,
        enterprise_baseline_version=enterprise_baseline.version if enterprise_baseline else None,
        enterprise_baseline_revision=enterprise_baseline.revision if enterprise_baseline else None,
        enterprise_baseline_sha256=enterprise_baseline.baseline_sha256 if enterprise_baseline else None,
        use_case_id=uc.use_case_id,
        use_case_name=uc.name,
        applicability_summary=applicability_summary,
        applicable_external_obligation_ids=applicable_external_ids,
        included_enterprise_clause_ids=sorted(included_clause_ids),
        excluded_enterprise_clause_ids=sorted(excluded_clause_ids),
        approved_reconciliation_ids=sorted(approved_rec_ids),
        stale_reconciliation_ids=sorted(stale_rec_ids),
        requirements=all_requirements,
        presentation_groups=presentation_groups,
        unresolved_items=unresolved_items,
        potential_conflicts=potential_conflicts,
        warnings=list(dict.fromkeys(warnings)),
        effective_baseline_sha256=effective_sha256,
    )
