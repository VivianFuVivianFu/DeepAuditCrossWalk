"""Facet-level questionnaire coverage engine."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Dict, List, Sequence, Set, Tuple

from .applicability import decide_applicability
from .models import (
    ApplicabilityStatus,
    AtomicObligation,
    Authority,
    BankingUseCase,
    CoverageAssessment,
    CoverageMetrics,
    CoverageStatus,
    GapRecord,
    GapType,
    MappingDecision,
    ObligationCoverage,
    QuestionBank,
    QuestionRecord,
    RegulatoryPack,
    ReviewStatus,
)


STOP_WORDS = {
    "about",
    "after",
    "against",
    "being",
    "does",
    "from",
    "have",
    "into",
    "must",
    "that",
    "their",
    "these",
    "this",
    "those",
    "through",
    "what",
    "when",
    "where",
    "which",
    "with",
    "within",
    "system",
    "control",
    "controls",
    "defined",
    "required",
    "relevant",
    "bank",
    "organisation",
    "organization",
}


def _tokens(text: str) -> Set[str]:
    return {
        item
        for item in re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
        if len(item) >= 3 and item not in STOP_WORDS
    }


def _domain_hints(facet: str) -> Set[str]:
    lower = facet.lower()
    hints: Set[str] = set()
    if any(
        word in lower
        for word in (
            "privacy",
            "personal",
            "collection",
            "consent",
            "retention",
            "disclosure",
        )
    ):
        hints.update({"privacy", "data-governance"})
    if any(word in lower for word in ("security", "incident", "vulnerab", "threat")):
        hints.update({"system-security", "privacy-security", "resilience"})
    if any(word in lower for word in ("complaint", "idr", "customer", "remediat")):
        hints.update({"contestability", "stakeholder", "accountability"})
    if any(
        word in lower for word in ("vendor", "provider", "third", "contract", "exit")
    ):
        hints.update({"vendor", "accountability"})
    if any(word in lower for word in ("human", "approval", "oversight")):
        hints.update({"oversight-governance", "human-centred-values", "contestability"})
    if any(word in lower for word in ("test", "robust", "accuracy", "continuity")):
        hints.update({"model-design-integrity", "reliability-safety", "resilience"})
    return hints


def _candidate_score(
    question: QuestionRecord, obligation: AtomicObligation, facet: str
) -> Tuple[float, str]:
    question_text = question.question_text.lower()
    keywords = obligation.facet_keywords.get(facet, [])
    phrase_hits = [keyword for keyword in keywords if keyword.lower() in question_text]

    target_tokens = _tokens(" ".join([facet, obligation.control_objective, *keywords]))
    question_tokens = _tokens(
        " ".join(
            [
                question.question_text,
                question.risk_domain or "",
                *question.response_tags,
            ]
        )
    )
    overlap = len(target_tokens & question_tokens) / max(len(target_tokens), 1)

    score = min(0.72, 0.22 * len(phrase_hits)) + min(0.42, overlap * 1.4)
    risk_domain = (question.risk_domain or "").lower().replace("ra:", "")
    if any(hint in risk_domain for hint in _domain_hints(facet)):
        score += 0.12
    if question.is_overlay:
        score += 0.04
    score = round(min(score, 0.99), 3)

    reasons: List[str] = []
    if phrase_hits:
        reasons.append("matched phrases: " + ", ".join(phrase_hits[:3]))
    if overlap:
        reasons.append(f"token overlap {overlap:.0%}")
    if risk_domain and any(hint in risk_domain for hint in _domain_hints(facet)):
        reasons.append(f"risk domain {question.risk_domain}")
    return score, "; ".join(reasons) or "weak semantic candidate"


def _status(required: Sequence[str], covered: Set[str]) -> CoverageStatus:
    if not required:
        return CoverageStatus.NOT_ASSESSED
    count = sum(facet in covered for facet in required)
    if count == len(required):
        return CoverageStatus.COVERED
    if count:
        return CoverageStatus.PARTIAL
    return CoverageStatus.MISSING


def _candidate_mappings(
    obligation: AtomicObligation,
    questions: Sequence[QuestionRecord],
    review_mappings: Sequence[MappingDecision],
    threshold: float = 0.34,
    limit_per_facet: int = 2,
) -> List[MappingDecision]:
    by_key: Dict[Tuple[str, str], MappingDecision] = {
        (mapping.facet, mapping.question_id): mapping
        for mapping in review_mappings
        if mapping.obligation_id == obligation.obligation_id
    }
    question_ids = {question.question_id for question in questions}
    output: List[MappingDecision] = []

    # Persisted human decisions always appear, including rejections, so the
    # audit report can explain why a tempting match did not count.
    for mapping in by_key.values():
        if (
            mapping.question_id in question_ids
            and mapping.facet in obligation.coverage_facets
        ):
            output.append(mapping)

    existing_keys = {(item.facet, item.question_id) for item in output}
    for facet in obligation.coverage_facets:
        scored: List[Tuple[float, str, QuestionRecord]] = []
        for question in questions:
            score, reason = _candidate_score(question, obligation, facet)
            if score >= threshold:
                scored.append((score, reason, question))
        scored.sort(key=lambda item: (-item[0], item[2].question_id))
        for score, reason, question in scored[:limit_per_facet]:
            key = (facet, question.question_id)
            if key in existing_keys:
                continue
            output.append(
                MappingDecision(
                    obligation_id=obligation.obligation_id,
                    facet=facet,
                    question_id=question.question_id,
                    review_status=ReviewStatus.PROPOSED,
                    confidence=score,
                    reason=reason,
                    source_reference=f"{question.source_sheet}:{question.question_id}",
                )
            )
            existing_keys.add(key)
    return output


def evaluate_questionnaire_coverage(
    *,
    tenant_id: str,
    use_case: BankingUseCase,
    question_bank: QuestionBank,
    regulatory_pack: RegulatoryPack,
    review_mappings: Sequence[MappingDecision] = (),
) -> CoverageAssessment:
    results: List[ObligationCoverage] = []

    for obligation in regulatory_pack.obligations:
        applicability = decide_applicability(obligation, use_case)
        if applicability.status is not ApplicabilityStatus.APPLICABLE:
            results.append(
                ObligationCoverage(
                    obligation_id=obligation.obligation_id,
                    instrument=obligation.instrument,
                    provision=obligation.provision,
                    title=obligation.title,
                    authority=obligation.authority,
                    source_url=obligation.source_url,
                    applicability=applicability,
                    confirmed_status=CoverageStatus.NOT_ASSESSED,
                    provisional_status=CoverageStatus.NOT_ASSESSED,
                    confirmed_missing_facets=list(obligation.coverage_facets),
                    provisional_missing_facets=list(obligation.coverage_facets),
                    evidence_requirements=obligation.evidence_requirements,
                )
            )
            continue

        mappings = _candidate_mappings(
            obligation, question_bank.questions, review_mappings
        )
        confirmed_facets = {
            mapping.facet
            for mapping in mappings
            if mapping.review_status is ReviewStatus.APPROVED
        }
        provisional_facets = {
            mapping.facet
            for mapping in mappings
            if mapping.review_status in {ReviewStatus.APPROVED, ReviewStatus.PROPOSED}
        }
        confirmed_missing = [
            facet
            for facet in obligation.coverage_facets
            if facet not in confirmed_facets
        ]
        provisional_missing = [
            facet
            for facet in obligation.coverage_facets
            if facet not in provisional_facets
        ]
        suggestions = [
            obligation.suggested_questions.get(facet)
            or f"How does the bank satisfy {facet.replace('_', ' ')} for this AI use case?"
            for facet in provisional_missing
        ]
        results.append(
            ObligationCoverage(
                obligation_id=obligation.obligation_id,
                instrument=obligation.instrument,
                provision=obligation.provision,
                title=obligation.title,
                authority=obligation.authority,
                source_url=obligation.source_url,
                applicability=applicability,
                confirmed_status=_status(obligation.coverage_facets, confirmed_facets),
                provisional_status=_status(
                    obligation.coverage_facets, provisional_facets
                ),
                confirmed_question_ids=sorted(
                    {
                        mapping.question_id
                        for mapping in mappings
                        if mapping.review_status is ReviewStatus.APPROVED
                    }
                ),
                candidate_question_ids=sorted(
                    {
                        mapping.question_id
                        for mapping in mappings
                        if mapping.review_status
                        in {ReviewStatus.APPROVED, ReviewStatus.PROPOSED}
                    }
                ),
                confirmed_missing_facets=confirmed_missing,
                provisional_missing_facets=provisional_missing,
                mappings=mappings,
                suggested_questions=list(dict.fromkeys(suggestions)),
                evidence_requirements=obligation.evidence_requirements,
            )
        )

    binding_authorities = {Authority.BINDING, Authority.ENFORCEABLE_GUIDANCE}
    applicable_binding = [
        item
        for item in results
        if item.applicability.status is ApplicabilityStatus.APPLICABLE
        and item.authority in binding_authorities
    ]
    confirmed_counts = defaultdict(int)
    provisional_counts = defaultdict(int)
    for item in applicable_binding:
        confirmed_counts[item.confirmed_status] += 1
        provisional_counts[item.provisional_status] += 1
    denominator = len(applicable_binding)
    metrics = CoverageMetrics(
        applicable_binding_obligations=denominator,
        confirmed_covered=confirmed_counts[CoverageStatus.COVERED],
        confirmed_partial=confirmed_counts[CoverageStatus.PARTIAL],
        confirmed_missing=confirmed_counts[CoverageStatus.MISSING],
        provisional_covered=provisional_counts[CoverageStatus.COVERED],
        provisional_partial=provisional_counts[CoverageStatus.PARTIAL],
        provisional_missing=provisional_counts[CoverageStatus.MISSING],
        applicability_conditional=sum(
            item.applicability.status is ApplicabilityStatus.CONDITIONAL
            for item in results
        ),
        applicability_undetermined=sum(
            item.applicability.status is ApplicabilityStatus.UNDETERMINED
            for item in results
        ),
        confirmed_coverage_rate=round(
            100 * confirmed_counts[CoverageStatus.COVERED] / denominator, 1
        )
        if denominator
        else 0.0,
        provisional_coverage_rate=round(
            100 * provisional_counts[CoverageStatus.COVERED] / denominator, 1
        )
        if denominator
        else 0.0,
    )
    assessment_id = str(uuid.uuid4())
    gaps: List[GapRecord] = []
    obligation_by_id = {
        item.obligation_id: item for item in regulatory_pack.obligations
    }
    for result in results:
        if (
            result.applicability.status is not ApplicabilityStatus.APPLICABLE
            or result.confirmed_status
            not in {CoverageStatus.PARTIAL, CoverageStatus.MISSING}
        ):
            continue
        obligation = obligation_by_id[result.obligation_id]
        severity = (
            "high"
            if result.authority in {Authority.BINDING, Authority.ENFORCEABLE_GUIDANCE}
            else "medium"
            if result.authority is Authority.ENTERPRISE
            else "low"
        )
        missing = result.confirmed_missing_facets
        candidate_only_facets = [
            facet for facet in missing if facet not in result.provisional_missing_facets
        ]
        genuinely_uncovered_facets = [
            facet for facet in missing if facet in result.provisional_missing_facets
        ]
        remediation_parts: List[str] = []
        if candidate_only_facets:
            remediation_parts.append(
                "Review and approve or reject the proposed question mappings for: "
                + ", ".join(candidate_only_facets)
                + "."
            )
        if genuinely_uncovered_facets:
            remediation_parts.extend(
                obligation.suggested_questions.get(facet)
                or f"How does the bank satisfy {facet.replace('_', ' ')} for this AI use case?"
                for facet in genuinely_uncovered_facets
            )
        gaps.append(
            GapRecord(
                gap_id=f"GAP-Q-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|{result.obligation_id}').hex[:16].upper()}",
                gap_type=GapType.QUESTIONNAIRE,
                title=f"Questionnaire coverage is not confirmed for {result.title}",
                severity=severity,
                obligation_id=result.obligation_id,
                missing_facets=missing,
                recommendation=" ".join(remediation_parts)
                or "Add or amend an AU_BANKING_OVERLAY question after control-owner review.",
                evidence_required=obligation.evidence_requirements,
                owner="Questionnaire Owner",
            )
        )

    selection_mode = question_bank.routing_metadata.get("selection_mode", "core_only")
    selection_warning = question_bank.routing_metadata.get("selection_warning")
    return CoverageAssessment(
        assessment_id=assessment_id,
        tenant_id=tenant_id,
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        routing_snapshot_id=question_bank.routing_metadata.get("routing_snapshot_id"),
        selected_question_ids=[item.question_id for item in question_bank.questions],
        use_case=use_case,
        metrics=metrics,
        results=results,
        gaps=gaps,
        question_scope="routed_snapshot"
        if selection_mode == "routed_snapshot"
        else "core_only",
        selected_question_count=len(question_bank.questions),
        selection_warning=selection_warning,
    )
