"""Facet-level questionnaire coverage engine."""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .applicability import decide_applicability
from .policy import (
    ABSENCE_OF_CONTROL_PATTERN,
    NEGATION_OR_EXEMPTION_PATTERN,
    PROHIBITION_BLOCK_PATTERN,
    THRESHOLD_AMOUNT_PATTERN,
    _detect_approval_timing,
    _detect_threshold_currency,
    _detect_threshold_operator,
    verify_baseline_integrity,
)
from .models import (
    ApplicabilityDecision,
    ClauseReviewStatus,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterpriseClauseCoverage,
    GapRecord,
    GapType,
    ApplicabilityStatus,
    AtomicObligation,
    Authority,
    BankingUseCase,
    CoverageAssessment,
    CoverageMetrics,
    CoverageStatus,
    LayerCoverageMetrics,
    MappingDecision,
    MappingRelationship,
    ObligationCoverage,
    QuestionBank,
    QuestionRecord,
    RegulatoryPack,
    ReviewStatus,
    authority_layer_bucket,
    utc_now,
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


def _layer_metrics_for(
    layer_key: str, items: Sequence[ObligationCoverage]
) -> LayerCoverageMetrics:
    applicable = [
        item
        for item in items
        if item.applicability.status is ApplicabilityStatus.APPLICABLE
    ]
    confirmed_counts = defaultdict(int)
    provisional_counts = defaultdict(int)
    for item in applicable:
        confirmed_counts[item.confirmed_status] += 1
        provisional_counts[item.provisional_status] += 1
    denominator = len(applicable)
    return LayerCoverageMetrics(
        layer_key=layer_key,
        applicable_obligations=denominator,
        confirmed_covered=confirmed_counts[CoverageStatus.COVERED],
        confirmed_partial=confirmed_counts[CoverageStatus.PARTIAL],
        confirmed_missing=confirmed_counts[CoverageStatus.MISSING],
        provisional_covered=provisional_counts[CoverageStatus.COVERED],
        provisional_partial=provisional_counts[CoverageStatus.PARTIAL],
        provisional_missing=provisional_counts[CoverageStatus.MISSING],
        applicability_conditional=sum(
            item.applicability.status is ApplicabilityStatus.CONDITIONAL
            for item in items
        ),
        applicability_undetermined=sum(
            item.applicability.status is ApplicabilityStatus.UNDETERMINED
            for item in items
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


def evaluate_questionnaire_coverage(
    *,
    tenant_id: str,
    use_case: Optional[BankingUseCase] = None,
    question_bank: QuestionBank,
    regulatory_pack: RegulatoryPack,
    review_mappings: Sequence[MappingDecision] = (),
    enterprise_baseline: Optional[EnterpriseBaseline] = None,
    enterprise_clauses: Sequence[EnterpriseClause] = (),
    assessment_mode: Optional[str] = None,
    assessment_target_type: str = "questionnaire",
) -> CoverageAssessment:
    use_case_was_omitted = use_case is None
    if use_case is None:
        use_case = BankingUseCase.enterprise_baseline()
    results: List[ObligationCoverage] = []

    # Step 3: Required invariant — if mode is omitted, it MUST resolve to regulatory_only
    if assessment_mode is None:
        effective_mode = "regulatory_only"
    else:
        effective_mode = assessment_mode

    if effective_mode not in {"regulatory_only", "enterprise_enhanced", "provisional"}:
        raise ValueError(f"Unsupported assessment mode '{effective_mode}'")

    if effective_mode == "regulatory_only":
        enterprise_baseline = None
        enterprise_clauses = ()
    elif effective_mode == "enterprise_enhanced":
        if enterprise_baseline is None and not enterprise_clauses:
            raise ValueError(
                "assessment_mode is 'enterprise_enhanced' but no eligible enterprise_baseline was provided. "
                "An explicit selected eligible enterprise baseline is required for enterprise_enhanced assessments."
            )
        if enterprise_baseline is not None:
            if enterprise_baseline.tenant_id != tenant_id:
                raise ValueError(
                    f"Cross-tenant baseline access rejected: baseline tenant '{enterprise_baseline.tenant_id}' "
                    f"does not match assessment tenant '{tenant_id}'"
                )
            if enterprise_baseline.status != "active":
                raise ValueError(
                    f"Enterprise baseline '{enterprise_baseline.baseline_id}' is in '{enterprise_baseline.status}' status. "
                    "Draft baselines cannot be selected for confirmed enterprise_enhanced assessments."
                )
            # Baseline eligibility check: must not be empty and must have at least one approved/confirmed clause
            has_approved = any(
                c.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
                for c in (enterprise_baseline.clause_snapshots or ())
            )
            if not has_approved:
                raise ValueError(
                    f"Enterprise baseline '{enterprise_baseline.baseline_id}' contains no approved or confirmed clauses "
                    "and is not eligible for enterprise_enhanced assessment."
                )
            if not verify_baseline_integrity(enterprise_baseline):
                raise ValueError(
                    f"Baseline integrity error: cryptographic fingerprint mismatch on baseline '{enterprise_baseline.baseline_id}'"
                )

    is_enterprise = effective_mode in {"enterprise_enhanced", "provisional"}

    # Resolve eligible external obligations from the Shared Regulatory Library.
    # Exclude all enterprise-specific obligations before applicability evaluation.
    external_obligations: List[AtomicObligation] = [
        ob
        for ob in regulatory_pack.obligations
        if ob.authority != Authority.ENTERPRISE
        and getattr(ob, "layer", None) != "enterprise_control_baseline"
        and getattr(ob, "source_id", "") != "ENTERPRISE-AI-STD"
        and ob.obligation_id != "ENT-AI-DELEGATED-APPROVAL"
    ]

    for obligation in external_obligations:
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
    layer_buckets = (
        "binding_regulatory",
        "regulatory_guidance",
        "voluntary_frameworks",
        "enterprise_internal_controls",
    )
    by_layer: Dict[str, LayerCoverageMetrics] = {
        bucket: _layer_metrics_for(
            bucket,
            [item for item in results if authority_layer_bucket(item.authority) == bucket],
        )
        for bucket in layer_buckets
    }
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
        by_authority_layer=by_layer,
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
                source_type="regulatory",
            )
        )

    applicable_obligation_ids = [
        item.obligation_id
        for item in results
        if item.applicability.status is ApplicabilityStatus.APPLICABLE
    ]

    selection_mode = question_bank.routing_metadata.get(
        "selection_mode", "full_questionnaire"
    )
    selection_warning = question_bank.routing_metadata.get("selection_warning")

    enterprise_gaps: List[GapRecord] = []
    enterprise_clause_coverage: List[EnterpriseClauseCoverage] = []
    applicable_enterprise_requirement_ids: List[str] = []

    if is_enterprise:
        source_clauses = (
            enterprise_baseline.clause_snapshots
            if enterprise_baseline and enterprise_baseline.clause_snapshots
            else enterprise_clauses
        )
        for clause in source_clauses:
            # Superseded or retired requirements must not silently influence active assessments
            if getattr(clause, "status", None) in {"superseded", "retired"}:
                continue

            # Rejected requirements must not contribute to confirmed coverage or gap calculations
            if clause.review_status == ClauseReviewStatus.REJECTED:
                continue

            # Proposed / pending requirements remain visible for reviewer follow-up but must not contribute to confirmed coverage
            is_pending = clause.review_status in {
                ClauseReviewStatus.PROPOSED,
                ClauseReviewStatus.UNREVIEWED,
            }
            is_approved = clause.review_status in {
                ClauseReviewStatus.APPROVED,
                ClauseReviewStatus.CONFIRMED,
            }

            # Determine Control Mapping approval status independently from Clause approval
            if clause.is_unmapped or not clause.control_mappings:
                control_mapping_status = ClauseReviewStatus.UNREVIEWED
            elif any(
                m.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
                and m.relationship in {MappingRelationship.FULL, MappingRelationship.PARTIAL}
                for m in clause.control_mappings
            ):
                control_mapping_status = ClauseReviewStatus.APPROVED
            elif all(
                m.review_status == ClauseReviewStatus.REJECTED
                for m in clause.control_mappings
            ):
                control_mapping_status = ClauseReviewStatus.REJECTED
            else:
                control_mapping_status = ClauseReviewStatus.PROPOSED

            impl_status = (
                clause.implementation_status
                if clause.implementation_status in {"implemented", "unimplemented", "unverified"}
                else "not_assessed"
            )

            # Non-mandatory or exempt clauses are recorded as NOT_APPLICABLE and do not generate false gaps
            if not clause.mandatory:
                enterprise_clause_coverage.append(
                    EnterpriseClauseCoverage(
                        clause_id=clause.clause_id,
                        policy_id=clause.policy_id,
                        source_name=clause.source_name,
                        applicability_status=ApplicabilityStatus.NOT_APPLICABLE,
                        clause_approval_status=clause.review_status,
                        control_mapping_approval_status=control_mapping_status,
                        questionnaire_to_facet_approval_status=ReviewStatus.UNREVIEWED,
                        coverage_status=CoverageStatus.NOT_APPLICABLE,
                        implementation_evidence_status=impl_status,
                        operational_effectiveness_status="not_assessed",
                        is_unmapped=clause.is_unmapped,
                        is_conditional=clause.is_conditional,
                        condition_description=clause.condition_description,
                        has_exception_clause=clause.has_exception_clause,
                        exception_description=clause.exception_description,
                        rationale=(
                            "Clause is non-mandatory or represents a policy exemption; excluded from mandatory coverage gaps."
                        ),
                    )
                )
                continue

            if is_approved:
                applicable_enterprise_requirement_ids.append(clause.clause_id)

            # Resolve required facets strictly from explicit clause facets or validated mapping facets.
            # Never assume all facets of a generic Unified Control apply or are satisfied merely because a Control ID is present.
            resolved_facets: List[str] = list(clause.control_facets)
            for m in clause.control_mappings:
                if (
                    m.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
                    and m.relationship in {MappingRelationship.FULL, MappingRelationship.PARTIAL}
                ):
                    for mf in getattr(m, "mapped_facets", []) or []:
                        if mf not in resolved_facets:
                            resolved_facets.append(mf)

            missing_facets: List[str] = []
            covered_facets: List[str] = []
            needs_review_facets: List[str] = []
            candidate_q_ids: List[str] = []
            confirmed_q_ids: List[str] = []

            if clause.is_unmapped or not clause.control_mappings:
                # Section 4: Approved unmapped requirements must keep the original clause visible,
                # preserve its source and approval, and mark the missing mapping relationship for review.
                # Do NOT use single-word keyword overlap to silently pass unmapped requirements.
                clause_cov_status = CoverageStatus.MAPPING_INCOMPLETE
                q_to_facet_status = ReviewStatus.UNREVIEWED
                missing_facets = ["mapping_incomplete", clause.clause_id]
                rationale = (
                    "Requirement is unmapped to a canonical control or validated facet specification; "
                    "human mapping review is required before coverage can be confirmed."
                )
            elif not resolved_facets:
                # Section 4 / Defect B: Mapped clause without explicit validated facets cannot silently bypass assessment.
                clause_cov_status = CoverageStatus.MAPPING_INCOMPLETE
                q_to_facet_status = ReviewStatus.UNREVIEWED
                missing_facets = ["mapping_incomplete"]
                rationale = (
                    "Clause has a control mapping but no explicit validated control facets; "
                    "cannot assume control facets are satisfied without facet-level resolution."
                )
            else:
                for facet in resolved_facets:
                    facet_satisfied = False
                    facet_has_weak_candidate = False
                    for q in question_bank.questions:
                        if _question_satisfies_enterprise_facet(facet, q.question_text, clause):
                            facet_satisfied = True
                            if q.question_id not in confirmed_q_ids:
                                confirmed_q_ids.append(q.question_id)
                            if q.question_id not in candidate_q_ids:
                                candidate_q_ids.append(q.question_id)
                        elif _question_is_weak_candidate_for_facet(facet, q.question_text):
                            facet_has_weak_candidate = True
                            if q.question_id not in candidate_q_ids:
                                candidate_q_ids.append(q.question_id)

                    if facet_satisfied:
                        covered_facets.append(facet)
                    else:
                        missing_facets.append(facet)
                        if facet_has_weak_candidate:
                            needs_review_facets.append(facet)

                # If clause specifies a required approval role, ensure at least one non-negated question satisfies that role
                if clause.required_approval_role:
                    role_satisfied = any(
                        not _is_question_negated_for_facet(q.question_text, "human_approval_required")
                        and _question_satisfies_approval_role(
                            q.question_text, clause.required_approval_role
                        )
                        for q in question_bank.questions
                    )
                    if not role_satisfied:
                        if "approval_authority_role" not in missing_facets:
                            missing_facets.append("approval_authority_role")
                        if (
                            "human_approval_required" in covered_facets
                        ):
                            covered_facets.remove("human_approval_required")
                            if "human_approval_required" not in missing_facets:
                                missing_facets.insert(0, "human_approval_required")

                if not missing_facets:
                    if is_approved and control_mapping_status in {
                        ClauseReviewStatus.APPROVED,
                        ClauseReviewStatus.CONFIRMED,
                    }:
                        clause_cov_status = CoverageStatus.COVERED
                        q_to_facet_status = ReviewStatus.APPROVED
                        rationale = "All required clause facets and deterministic constraints are satisfied."
                    else:
                        clause_cov_status = CoverageStatus.NEEDS_REVIEW
                        q_to_facet_status = ReviewStatus.PROPOSED
                        rationale = (
                            "Candidate questions satisfy clause facets, but clause or control mapping approval is still pending."
                        )
                elif covered_facets:
                    if needs_review_facets:
                        clause_cov_status = CoverageStatus.NEEDS_REVIEW
                        q_to_facet_status = ReviewStatus.PROPOSED
                    else:
                        clause_cov_status = CoverageStatus.PARTIAL
                        q_to_facet_status = ReviewStatus.PROPOSED
                    rationale = (
                        f"Some required facets are satisfied ({covered_facets}), but required facets remain unresolved ({missing_facets})."
                    )
                elif needs_review_facets or candidate_q_ids:
                    clause_cov_status = CoverageStatus.NEEDS_REVIEW
                    q_to_facet_status = ReviewStatus.PROPOSED
                    rationale = (
                        "Candidate question text touches related concepts, but semantic and constraint sufficiency is not established."
                    )
                else:
                    clause_cov_status = CoverageStatus.MISSING
                    q_to_facet_status = ReviewStatus.UNREVIEWED
                    rationale = "No candidate question in the assessed questionnaire addresses the required facets."

            enterprise_clause_coverage.append(
                EnterpriseClauseCoverage(
                    clause_id=clause.clause_id,
                    policy_id=clause.policy_id,
                    source_name=clause.source_name,
                    applicability_status=(
                        ApplicabilityStatus.CONDITIONAL
                        if clause.is_conditional
                        else ApplicabilityStatus.APPLICABLE
                    ),
                    clause_approval_status=clause.review_status,
                    control_mapping_approval_status=control_mapping_status,
                    questionnaire_to_facet_approval_status=q_to_facet_status,
                    coverage_status=clause_cov_status,
                    implementation_evidence_status=impl_status,
                    operational_effectiveness_status="not_assessed",
                    required_facets=resolved_facets,
                    covered_facets=covered_facets,
                    missing_facets=missing_facets,
                    needs_review_facets=needs_review_facets,
                    candidate_question_ids=candidate_q_ids,
                    confirmed_question_ids=confirmed_q_ids,
                    is_unmapped=clause.is_unmapped,
                    is_conditional=clause.is_conditional,
                    condition_description=clause.condition_description,
                    has_exception_clause=clause.has_exception_clause,
                    exception_description=clause.exception_description,
                    rationale=rationale,
                )
            )

            if missing_facets:
                is_voluntary = (
                    clause.authority_level.value == "industry_framework"
                    if hasattr(clause.authority_level, "value")
                    else str(clause.authority_level) == "industry_framework"
                )
                severity = "low" if is_voluntary else "medium"
                if (
                    is_pending
                    or clause_cov_status
                    in {CoverageStatus.MAPPING_INCOMPLETE, CoverageStatus.NEEDS_REVIEW}
                ):
                    gap_status = "in_review" if (is_pending or clause_cov_status == CoverageStatus.MAPPING_INCOMPLETE) else "open"
                else:
                    gap_status = "open"

                egap = GapRecord(
                    gap_id=f"GAP-E-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|{clause.clause_id}').hex[:16].upper()}",
                    gap_type=GapType.QUESTIONNAIRE,
                    title=(
                        f"Pending review: questionnaire does not test candidate enterprise requirement ({clause.clause_id})"
                        if is_pending
                        else f"Mapping incomplete: enterprise requirement requires facet/mapping review ({clause.clause_id})"
                        if clause_cov_status == CoverageStatus.MAPPING_INCOMPLETE
                        else f"Needs review: candidate question insufficient for enterprise requirement ({clause.clause_id})"
                        if clause_cov_status == CoverageStatus.NEEDS_REVIEW
                        else f"Questionnaire does not test approved enterprise requirement ({clause.clause_id})"
                    ),
                    status=gap_status,
                    severity=severity,
                    coverage_status=clause_cov_status,
                    policy_clause_id=clause.clause_id,
                    missing_facets=missing_facets,
                    recommendation=f"Add a question testing enterprise policy requirement '{clause.clause_id}' ({clause.source_name}).",
                    evidence_required=["Approved policy clause", "Question-to-policy mapping review"],
                    owner="Enterprise Policy Owner",
                    source_type="enterprise_policy",
                )
                enterprise_gaps.append(egap)
                gaps.append(egap)

        # ─────────────────────────────────────────────────────────────────────
        # Numeric Approval Threshold & Control Constraint Validation (Prompt 2D)
        # ─────────────────────────────────────────────────────────────────────
        # Filter for approved mandatory enterprise clauses with thresholds or approval constraints
        approved_mandatory_clauses = [
            c
            for c in source_clauses
            if c.mandatory
            and c.review_status
            in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
        ]

        # 1. Baseline Internal Conflict Check across approved clauses
        threshold_map: Dict[float, List[EnterpriseClause]] = defaultdict(list)
        for c in approved_mandatory_clauses:
            for t in c.thresholds_aud:
                threshold_map[t].append(c)

        observed_thresholds = sorted(threshold_map.keys())
        if len(observed_thresholds) > 1:
            conflict_gap = GapRecord(
                gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|internal_threshold_conflict').hex[:16].upper()}",
                gap_type=GapType.CONTROL_CONFLICT,
                title="Enterprise policies contain conflicting AUD approval thresholds",
                severity="high",
                missing_facets=["single_authoritative_threshold"],
                recommendation=f"Reconcile contradictory thresholds across approved policies: {observed_thresholds}.",
                evidence_required=["Approved delegated-authority schedule"],
                source_type="internal_conflict",
                required_threshold=observed_thresholds[0],
                use_case_threshold=observed_thresholds[1],
            )
            enterprise_gaps.append(conflict_gap)
            gaps.append(conflict_gap)

        # 2. Use-Case Threshold & Constraint Validation against approved clauses
        for clause in approved_mandatory_clauses:
            policy_threshold = (
                clause.thresholds_aud[0] if clause.thresholds_aud else None
            )
            policy_operator = clause.threshold_operator or ">"
            policy_currency = clause.threshold_currency or "AUD"
            policy_timing = clause.approval_timing
            policy_role = clause.required_approval_role

            # If clause has an implementation status of 'unimplemented' (Category D)
            if clause.implementation_status == "unimplemented":
                unimplemented_gap = GapRecord(
                    gap_id=f"GAP-E-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|unimplemented|{clause.clause_id}').hex[:16].upper()}",
                    gap_type=GapType.IMPLEMENTATION_EVIDENCE,
                    title=f"Mandatory enterprise control is marked unimplemented in policy workflow ({clause.clause_id})",
                    status="open",
                    severity="high",
                    policy_clause_id=clause.clause_id,
                    missing_facets=list(clause.control_facets),
                    recommendation=f"Deploy the operational approval workflow required by {clause.source_name} ({clause.clause_id}).",
                    evidence_required=[
                        "Production deployment verification",
                        "Operational workflow trace",
                    ],
                    owner="Engineering & Controls Owner",
                    source_type="enterprise_policy",
                    evidence_missing=True,
                )
                enterprise_gaps.append(unimplemented_gap)
                gaps.append(unimplemented_gap)

            # If policy has a threshold requirement:
            if policy_threshold is not None:
                use_case_threshold = use_case.approval_threshold_aud
                use_case_operator = use_case.approval_threshold_operator or ">"
                use_case_currency = use_case.approval_threshold_currency or "AUD"

                # Check 1: Missing use-case threshold (Scenario 5)
                if use_case_threshold is None:
                    missing_t_gap = GapRecord(
                        gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|missing_threshold|{clause.clause_id}').hex[:16].upper()}",
                        gap_type=GapType.CONTROL_CONFLICT,
                        title=f"Use-case approval threshold is not configured; cannot verify compliance with {clause.clause_id}",
                        status="open",
                        severity="medium",
                        policy_clause_id=clause.clause_id,
                        missing_facets=["approval_threshold_defined"],
                        recommendation=(
                            f"Configure the use-case approval threshold to demonstrate compliance with "
                            f"{clause.source_name} requirement of {policy_currency} {policy_threshold:g}."
                        ),
                        evidence_required=[
                            "Delegated-authority schedule",
                            "System configuration",
                        ],
                        owner="Use Case Owner",
                        source_type="enterprise_policy",
                        required_threshold=policy_threshold,
                        threshold_operator=policy_operator,
                        evidence_missing=True,
                    )
                    enterprise_gaps.append(missing_t_gap)
                    gaps.append(missing_t_gap)

                # Check 2: Currency mismatch (Scenario 6)
                elif policy_currency != use_case_currency:
                    curr_gap = GapRecord(
                        gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|currency_mismatch|{clause.clause_id}').hex[:16].upper()}",
                        gap_type=GapType.CONTROL_CONFLICT,
                        title=f"Approval threshold currency mismatch for {clause.clause_id}",
                        status="open",
                        severity="high",
                        policy_clause_id=clause.clause_id,
                        missing_facets=["currency_conversion_verified"],
                        recommendation=(
                            f"Enterprise policy threshold is defined in {policy_currency} {policy_threshold:g}, "
                            f"but use-case is configured in {use_case_currency} {use_case_threshold:g}. "
                            f"Automated equivalence cannot be assumed without an approved currency conversion rate."
                        ),
                        evidence_required=[
                            "Approved FX policy",
                            "System multi-currency configuration",
                        ],
                        owner="Treasury / Risk Owner",
                        source_type="enterprise_policy",
                        required_threshold=policy_threshold,
                        use_case_threshold=use_case_threshold,
                        evidence_missing=True,
                    )
                    enterprise_gaps.append(curr_gap)
                    gaps.append(curr_gap)

                # Check 3: Numeric threshold comparison (Scenario 1, 2, 3, 4, 7, 8)
                else:
                    is_looser = use_case_threshold > policy_threshold
                    is_boundary_mismatch = (
                        use_case_threshold == policy_threshold
                        and policy_operator == ">="
                        and use_case_operator == ">"
                    )

                    if is_looser or is_boundary_mismatch:
                        has_exception = bool(use_case.has_approved_exception)
                        status_str = "in_review" if has_exception else "open"
                        severity_str = "medium" if has_exception else "critical"

                        title_reason = (
                            f"Configured approval threshold ({use_case_currency} {use_case_threshold:g}) exceeds approved policy threshold ({policy_currency} {policy_threshold:g})"
                            if is_looser
                            else f"Configured threshold boundary operator ('{use_case_operator}') fails to cover exact boundary for '{policy_operator} {policy_currency} {policy_threshold:g}'"
                        )
                        rec_str = (
                            f"Align system threshold {use_case_operator} {use_case_currency} {use_case_threshold:g} to policy requirement "
                            f"{policy_operator} {policy_currency} {policy_threshold:g} (exposure interval: {policy_threshold:g} to {use_case_threshold:g}), or obtain an authorised policy exception."
                            if is_looser
                            else f"Update use-case operator from '{use_case_operator}' to '{policy_operator}' to prevent unapproved execution at boundary value {policy_currency} {policy_threshold:g}."
                        )
                        if has_exception:
                            rec_str += f" [Documented Exception: {use_case.exception_reference or 'Authorised'}]"

                        t_gap = GapRecord(
                            gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|threshold_mismatch|{clause.clause_id}').hex[:16].upper()}",
                            gap_type=GapType.CONTROL_CONFLICT,
                            title=title_reason,
                            status=status_str,
                            severity=severity_str,
                            policy_clause_id=clause.clause_id,
                            missing_facets=["approval_threshold_aligned"],
                            recommendation=rec_str,
                            evidence_required=[
                                "Delegated-authority policy",
                                "Production configuration",
                                *(
                                    [
                                        f"Authorised exception ({use_case.exception_reference})"
                                    ]
                                    if has_exception
                                    else ["Exception approval"]
                                ),
                            ],
                            owner="Use Case Controls Owner",
                            source_type="enterprise_policy",
                            required_threshold=policy_threshold,
                            use_case_threshold=use_case_threshold,
                            threshold_operator=policy_operator,
                            use_case_operator=use_case_operator,
                            evidence_missing=not has_exception,
                        )
                        enterprise_gaps.append(t_gap)
                        gaps.append(t_gap)

            # Check 4: Approval Timing (Scenario 10)
            if (
                policy_timing == "pre_execution"
                and use_case.approval_timing == "post_execution"
            ):
                timing_gap = GapRecord(
                    gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|timing_mismatch|{clause.clause_id}').hex[:16].upper()}",
                    gap_type=GapType.CONTROL_CONFLICT,
                    title=f"Approval timing mismatch for {clause.clause_id}: pre-execution block required",
                    status="open",
                    severity="critical",
                    policy_clause_id=clause.clause_id,
                    missing_facets=["pre_execution_block"],
                    recommendation=(
                        f"Enterprise policy '{clause.source_name}' mandates pre-execution blocking approval, "
                        f"but use-case is configured for post-execution review. Configure a pre-execution blocking control."
                    ),
                    evidence_required=[
                        "Pre-execution control configuration",
                        "Execution blocking test trace",
                    ],
                    owner="Engineering & Architecture",
                    source_type="enterprise_policy",
                    timing_required="pre_execution",
                    use_case_timing="post_execution",
                    evidence_missing=True,
                )
                enterprise_gaps.append(timing_gap)
                gaps.append(timing_gap)

            # Check 5: Approval Authority Role (Scenario 11)
            if (
                policy_role
                and use_case.approval_role
                and policy_role.lower() != use_case.approval_role.lower()
            ):
                role_gap = GapRecord(
                    gap_id=f"GAP-C-{uuid.uuid5(uuid.NAMESPACE_URL, f'{assessment_id}|role_mismatch|{clause.clause_id}').hex[:16].upper()}",
                    gap_type=GapType.CONTROL_CONFLICT,
                    title=f"Approval authority role mismatch for {clause.clause_id}: {policy_role} required",
                    status="open",
                    severity="high",
                    policy_clause_id=clause.clause_id,
                    missing_facets=["delegated_authority_role_aligned"],
                    recommendation=(
                        f"Enterprise policy '{clause.source_name}' requires '{policy_role}' approval, "
                        f"but use-case specifies '{use_case.approval_role}'. Elevate approval routing to '{policy_role}'."
                    ),
                    evidence_required=[
                        "Delegated authority schedule",
                        "Role-based access control configuration",
                    ],
                    owner="Delegated Authority Owner",
                    source_type="enterprise_policy",
                    role_required=policy_role,
                    use_case_role=use_case.approval_role,
                    evidence_missing=True,
                )
                enterprise_gaps.append(role_gap)
                gaps.append(role_gap)

    provenance = {
        "assessment_mode": effective_mode,
        "assessment_target_type": assessment_target_type,
        "tenant_id": tenant_id,
        "regulatory_pack_id": regulatory_pack.pack_id,
        "regulatory_pack_version": regulatory_pack.version,
        "unified_control_library_version": "2026.1",
        "enterprise_baseline_id": enterprise_baseline.baseline_id if (is_enterprise and enterprise_baseline) else None,
        "enterprise_baseline_version": enterprise_baseline.version if (is_enterprise and enterprise_baseline) else None,
        "enterprise_baseline_revision": enterprise_baseline.revision if (is_enterprise and enterprise_baseline) else None,
        "baseline_sha256": enterprise_baseline.baseline_sha256 if (is_enterprise and enterprise_baseline) else None,
        "applicable_obligation_count": len(applicable_obligation_ids),
        "applicable_enterprise_requirement_count": len(applicable_enterprise_requirement_ids),
        "timestamp": utc_now().isoformat(),
    }

    return CoverageAssessment(
        assessment_id=assessment_id,
        tenant_id=tenant_id,
        created_at=utc_now(),
        assessment_mode=effective_mode,
        assessment_target_type=assessment_target_type,
        questionnaire_id=question_bank.metadata.questionnaire_id,
        questionnaire_sha256=question_bank.metadata.source_sha256,
        regulatory_pack_id=regulatory_pack.pack_id,
        regulatory_pack_version=regulatory_pack.version,
        unified_control_library_version="2026.1",
        routing_snapshot_id=question_bank.routing_metadata.get("routing_snapshot_id"),
        selected_question_ids=[item.question_id for item in question_bank.questions],
        use_case=use_case,
        metrics=metrics,
        results=results,
        gaps=gaps,
        question_scope="routed_snapshot"
        if selection_mode == "routed_snapshot"
        else "core_only"
        if selection_mode == "core_only"
        else "full_questionnaire",
        selected_question_count=len(question_bank.questions),
        selection_warning=selection_warning,
        enterprise_baseline_id=enterprise_baseline.baseline_id if (is_enterprise and enterprise_baseline) else None,
        enterprise_baseline_version=enterprise_baseline.version if (is_enterprise and enterprise_baseline) else None,
        enterprise_baseline_revision=enterprise_baseline.revision if (is_enterprise and enterprise_baseline) else None,
        enterprise_gaps=enterprise_gaps if is_enterprise else [],
        enterprise_clause_coverage=enterprise_clause_coverage if is_enterprise else [],
        applicable_obligation_ids=applicable_obligation_ids,
        applicable_enterprise_requirement_ids=applicable_enterprise_requirement_ids if is_enterprise else [],
        legal_disclaimer="Assessment gaps do not constitute judicial or regulatory findings of legal non-compliance.",
        provenance=provenance,
    )


def _is_question_negated_for_facet(q_text: str, facet: str) -> bool:
    """Return True if the question text explicitly negates or exempts the control."""
    if facet == "zero_data_retention":
        return False
    if ABSENCE_OF_CONTROL_PATTERN.search(q_text):
        return True
    if NEGATION_OR_EXEMPTION_PATTERN.search(q_text) and not PROHIBITION_BLOCK_PATTERN.search(
        q_text
    ):
        return True
    return False


def _question_satisfies_approval_role(q_text: str, required_role: str) -> bool:
    """Verify whether the question explicitly tests the required approval authority role."""
    lower = q_text.lower()
    req_lower = required_role.lower()
    if req_lower == "senior manager":
        return "senior manager" in lower or "executive" in lower
    if req_lower in ("authorised officer", "authorized officer"):
        return (
            "authorised officer" in lower
            or "authorized officer" in lower
            or "delegated authority" in lower
        )
    if "two-up" in req_lower or "dual" in req_lower:
        return any(
            p in lower
            for p in (
                "dual sign-off",
                "dual human sign-off",
                "dual approval",
                "two-up",
                "four-eyes",
            )
        )
    return req_lower in lower


def _question_satisfies_enterprise_facet(
    facet: str, q_text: str, clause: EnterpriseClause
) -> bool:
    """Deterministically verify whether a question satisfies a required enterprise facet and its constraints."""
    if _is_question_negated_for_facet(q_text, facet):
        return False

    ql = q_text.lower()

    if facet == "human_approval_required":
        explicit_approval_phrases = (
            "human approval",
            "manual approval",
            "approved by a human",
            "human sign-off",
            "dual sign-off",
            "dual human sign-off",
            "dual approval",
            "manager approval",
            "manager sign-off",
            "authorised officer approval",
            "authorized officer approval",
            "officer sign-off",
            "supervisor approval",
        )
        if not any(p in ql for p in explicit_approval_phrases):
            return False
        if clause.required_approval_role:
            if not _question_satisfies_approval_role(q_text, clause.required_approval_role):
                return False
        return True

    if facet == "approval_threshold_defined":
        if not any(
            t in ql
            for t in (
                "approval",
                "sign-off",
                "refund",
                "payment",
                "transaction",
                "credit",
                "limit",
                "adjustment",
                "threshold",
            )
        ):
            return False

        if clause.thresholds_aud:
            q_amounts = [
                float(m.replace(",", ""))
                for m in THRESHOLD_AMOUNT_PATTERN.findall(q_text)
            ]
            if not q_amounts:
                return False
            req_curr = (clause.threshold_currency or "AUD").upper()
            q_curr = (_detect_threshold_currency(q_text) or "AUD").upper()
            if q_curr != req_curr:
                return False

            req_op = clause.threshold_operator or ">"
            q_op = _detect_threshold_operator(q_text) or ">"
            for req_amt in clause.thresholds_aud:
                amt_satisfied = False
                for q_amt in q_amounts:
                    if q_amt < req_amt:
                        amt_satisfied = True
                        break
                    if q_amt == req_amt:
                        if req_op == ">=" and q_op == ">":
                            continue
                        amt_satisfied = True
                        break
                if not amt_satisfied:
                    return False
            return True

        return any(
            p in ql
            for p in (
                "approval threshold",
                "monetary threshold",
                "delegated authority threshold",
                "financial threshold",
            )
        )

    if facet == "pre_execution_block":
        if _detect_approval_timing(q_text) == "post_execution" or any(
            p in ql
            for p in (
                "post-execution",
                "post execution",
                "after execution",
                "after payment",
                "retrospective",
            )
        ):
            return False
        pre_exec_phrases = (
            "before payment",
            "before execution",
            "prior to payment",
            "prior to execution",
            "prior to transaction",
            "prior to approval",
            "must not execute",
            "shall not execute",
            "cannot proceed",
            "cannot execute",
            "blocked prior to",
            "pre-execution block",
            "pre-execution",
            "prevent execution",
        )
        return any(p in ql for p in pre_exec_phrases)

    if facet in ("prompt_logging", "prompt_logging_enabled"):
        prompt_log_phrases = (
            "prompt logging",
            "log all prompts",
            "prompt and output log",
            "interaction logs",
            "llm telemetry",
            "prompt telemetry",
            "prompt audit log",
        )
        return any(p in ql for p in prompt_log_phrases)

    if facet == "zero_data_retention":
        return any(
            p in ql
            for p in (
                "zero data retention",
                "no data retention",
                "do not retain",
                "not retain customer data",
                "zero-retention",
            )
        )

    if facet == "data_sovereignty":
        return any(
            p in ql
            for p in (
                "data sovereignty",
                "sovereign cloud",
                "on-shore",
                "australian data center",
                "australian data centre",
                "stored within australia",
                "cross-border data",
            )
        )

    if facet == "bias_testing":
        return any(
            p in ql
            for p in (
                "bias testing",
                "algorithmic bias",
                "fairness testing",
                "demographic parity",
                "disparate impact",
                "protected attributes",
            )
        )

    if facet == "model_inventory":
        return any(
            p in ql
            for p in (
                "ai inventory",
                "model inventory",
                "model registry",
                "use case register",
                "ai catalog",
                "model card",
            )
        )

    return facet.replace("_", " ").lower() in ql


def _question_is_weak_candidate_for_facet(facet: str, q_text: str) -> bool:
    """Return True if a non-negated question touches related topical concepts without satisfying the facet."""
    if _is_question_negated_for_facet(q_text, facet):
        return False

    ql = q_text.lower()
    weak_cues_by_facet: Dict[str, Tuple[str, ...]] = {
        "human_approval_required": (
            "human oversight",
            "human review",
            "manual review",
            "human-in-the-loop",
            "human approval",
            "approval",
            "sign-off",
            "oversight",
        ),
        "approval_threshold_defined": (
            "threshold",
            "high-value",
            "defined",
            "approval",
            "limit",
            "exceeding",
            "aud",
        ),
        "pre_execution_block": (
            "execution",
            "executions",
            "block",
            "prior to",
            "before",
            "post-execution",
            "override",
        ),
        "prompt_logging": ("log", "logs", "logging", "telemetry", "traceability", "audit"),
        "prompt_logging_enabled": ("log", "logs", "logging", "telemetry", "traceability", "audit"),
        "zero_data_retention": ("retention", "retain", "deletion", "disposal"),
        "data_sovereignty": (
            "sovereignty",
            "cross-border",
            "jurisdiction",
            "offshore",
            "data center",
            "data centre",
        ),
        "bias_testing": ("bias", "fairness", "discrimination", "equitable"),
        "model_inventory": ("inventory", "registry", "register", "catalog", "catalogue"),
    }
    cues = weak_cues_by_facet.get(facet, (facet.replace("_", " ").lower(),))
    return any(cue in ql for cue in cues)
