"""Hybrid Semantic Reconciliation (E3): Stage A-D Pipeline & Questionnaire Candidate Harness.

Pipeline:
  Stage A (Candidate Retrieval) -> Embedding similarity fused with deterministic signals
  Stage B (Semantic Interpretation) -> Schema-validated LLM analysis with strict citations
  Stage C (Deterministic Validation) -> Authoritative E1 Stage B checks with veto power
  Stage D (Human Review) -> Always emits PROPOSED or NEEDS_REVIEW; never auto-approves

Also provides `suggest_questionnaire_mappings_hybrid()` reusing the same
provider-agnostic abstraction without altering or bypassing the production
Questionnaire Coverage Engine.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .applicability import select_applicable_obligations
from .catalog import (
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_unified_control_library,
)
from .llm import (
    CitationVerificationError,
    ConfidentialityPolicyError,
    DataClassification,
    LLMProviderError,
    LLMProviderKind,
    LLMRuntimeConfig,
    ProviderConfigurationError,
    QuestionnaireSemanticMatchAnalysis,
    SemanticMatchingMode,
    SemanticProviderBundle,
    SemanticRelationshipAnalysis,
    build_provider_bundle,
    enforce_runtime_confidentiality,
    sanitize_untrusted_text,
    scrub_secrets,
    validate_semantic_citation,
)
from .llm.providers import _cosine_similarity
from .models import (
    ApplicabilityStatus,
    AtomicObligation,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingDecision,
    MappingRelationship,
    ObligationControlMappingCatalogue,
    QuestionBank,
    ReconciliationDecision,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
    RegulatoryPack,
    ReviewStatus,
    UnifiedControlLibrary,
)
from .reconciliation import (
    ENTERPRISE_GENERIC_FACETS,
    _NON_REGULATORY_CORPORATE_NOISE_PATTERN,
    _compare_obligation_bound_timeframes,
    _detect_action_polarity,
    _detect_external_timing,
    _detect_internal_enterprise_conflicts,
    _detect_operational_scopes,
    _deterministic_reconciliation_id,
    _expand_control_ids,
    _extract_currency_and_amounts,
    _extract_timeframe_hours,
    _infer_canonical_obligation_facets_for_clause,
    _is_ambiguous_clause,
    _match_topic_obligations_for_unmapped_or_negative_clause,
    compute_clause_sha256,
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
    validate_candidate_relationship,
)
from .coverage import _tokens as _policy_tokens
from .policy import (
    _detect_approval_role,
    _detect_approval_timing,
    _detect_threshold_currency,
    _detect_threshold_operator,
)


_EXPLICIT_CITATION_TOKENS: Tuple[str, ...] = (
    "app 1",
    "app 3",
    "app 5",
    "app 6",
    "app 8",
    "app 11",
    "app 12",
    "app 13",
    "cps 234",
    "cps 230",
    "cps 220",
    "cps 510",
    "rg 271",
    "rep 798",
    "nccp",
    "s 128",
    "s 16c",
    "s 26we",
    "oaic",
)


def _format_obligation_embedding_text(ob: AtomicObligation) -> str:
    facets_txt = ", ".join(ob.coverage_facets or [])
    return (
        f"{ob.instrument} {ob.provision} — {ob.title}. "
        f"{ob.concise_obligation_summary} "
        f"Control objective: {ob.control_objective or ''}. "
        f"Facets: {facets_txt}."
    )


def _has_explicit_citation(text: str) -> bool:
    lower = (text or "").lower()
    return any(tok in lower for tok in _EXPLICIT_CITATION_TOKENS)


def retrieve_reconciliation_candidates_hybrid(
    clause: EnterpriseClause,
    *,
    regulatory_pack: Optional[RegulatoryPack] = None,
    control_library: Optional[UnifiedControlLibrary] = None,
    obligation_mappings: Optional[ObligationControlMappingCatalogue] = None,
    use_case: Optional[BankingUseCase] = None,
    include_non_applicable: bool = False,
    bundle: Optional[SemanticProviderBundle] = None,
    data_classification: DataClassification = DataClassification.CONFIDENTIAL_ENTERPRISE,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Stage A Hybrid Candidate Retrieval (Embedding + Deterministic Baseline + Fallback)."""
    reg_pack = regulatory_pack or load_regulatory_pack()
    ctrl_lib = control_library or load_unified_control_library()
    ob_map_cat = obligation_mappings or load_obligation_control_mappings()

    det_ranked = rank_reconciliation_candidates_for_clause(
        clause=clause,
        regulatory_pack=reg_pack,
        control_library=ctrl_lib,
        obligation_mappings=ob_map_cat,
        use_case=use_case,
        include_non_applicable=include_non_applicable,
        top_k=max(top_k, 12),
    )
    det_by_id = {item["obligation_id"]: item for item in det_ranked}

    applicable_obs: List[AtomicObligation] = list(reg_pack.obligations)
    if use_case is not None and not include_non_applicable:
        app_decisions = select_applicable_obligations(reg_pack.obligations, use_case)
        app_ids = {
            d.obligation_id
            for d in app_decisions
            if d.status
            in {
                ApplicabilityStatus.APPLICABLE,
                ApplicabilityStatus.CONDITIONAL,
                ApplicabilityStatus.UNDETERMINED,
            }
        }
        applicable_obs = [ob for ob in reg_pack.obligations if ob.obligation_id in app_ids]

    src_map = {s.source_id: s for s in reg_pack.sources}
    emb_scores: Dict[str, float] = {}
    retrieval_mode = "deterministic_only"
    fallback_reason: Optional[str] = None

    if (
        bundle is not None
        and bundle.config.semantic_matching_enabled
        and bundle.embedding_provider is not None
        and bundle.embedding_provider.supports_embeddings
        and applicable_obs
    ):
        enforce_runtime_confidentiality(
            bundle.config,
            data_classification=data_classification,
            tenant_id=clause.tenant_id,
        )
        try:
            ob_texts = [_format_obligation_embedding_text(ob) for ob in applicable_obs]
            ob_vecs = bundle.embed_with_cache(
                ob_texts,
                task_type="RETRIEVAL_DOCUMENT",
                data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
                tenant_id=clause.tenant_id,
            )
            clause_vec = bundle.embed_with_cache(
                [clause.text],
                task_type="RETRIEVAL_QUERY",
                data_classification=data_classification,
                tenant_id=clause.tenant_id,
            )[0]
            for ob, vec in zip(applicable_obs, ob_vecs):
                raw_sim = _cosine_similarity(clause_vec, vec)
                emb_scores[ob.obligation_id] = round(max(0.0, raw_sim), 4)
            retrieval_mode = "hybrid_embedding_plus_deterministic"
        except (ConfidentialityPolicyError, ProviderConfigurationError):
            raise
        except LLMProviderError as exc:
            bundle.telemetry.fallback_events += 1
            fallback_reason = scrub_secrets(str(exc))
            retrieval_mode = "deterministic_fallback"
            if fallback_reason not in bundle.telemetry.notes:
                bundle.telemetry.notes.append(f"Stage A embedding fallback: {fallback_reason}")

    c_lower = (clause.text or "").lower()
    if _NON_REGULATORY_CORPORATE_NOISE_PATTERN.search(c_lower) and not det_by_id:
        return {
            "candidates": [],
            "all_emb_scores": emb_scores,
            "retrieval_mode": retrieval_mode,
            "fallback_reason": fallback_reason,
        }
    has_eu_cue = any(
        w in c_lower
        for w in ("eu ai act", "article 26", "article 27", "article 50", "annex iii", "fria", "eur ", "eur$")
    )
    has_au_cue = any(
        w in c_lower
        for w in ("aud", "apra", "oaic", "asic", "nccp", "app ", "cps ", "cpg ", "rg 271", "rep 798", "authorised officer", "australia")
    )

    fused: List[Dict[str, Any]] = []
    for ob in applicable_obs:
        oid = ob.obligation_id
        det_item = det_by_id.get(oid)
        det_score = float(det_item["score"]) if det_item else 0.0
        emb_score = emb_scores.get(oid)

        reasons: List[str] = list(det_item["reasons"]) if det_item else []
        if emb_score is not None:
            if det_score >= 0.35:
                hybrid_score = 0.42 * emb_score + 0.58 * det_score
            elif det_score > 0.0:
                hybrid_score = 0.62 * emb_score + 0.38 * det_score
            else:
                hybrid_score = emb_score * 0.96
            if emb_score >= 0.30:
                reasons.append(f"Semantic embedding cosine={emb_score:.3f}")
        else:
            hybrid_score = det_score

        if has_au_cue and not has_eu_cue:
            if ob.jurisdiction == "AU":
                hybrid_score += 0.06
            elif ob.jurisdiction == "EU":
                hybrid_score = max(0.0, hybrid_score - 0.14)
        elif has_eu_cue and ob.jurisdiction == "EU":
            hybrid_score += 0.10

        if hybrid_score <= 0.08:
            continue

        src = src_map.get(ob.source_id)
        source_ref = {
            "source_id": ob.source_id,
            "source_title": src.title if src else ob.instrument,
            "source_version": (src.version_id or src.version) if src else ob.version,
            "provision": ob.provision,
            "obligation_id": oid,
        }
        fused.append(
            {
                "obligation_id": oid,
                "obligation": ob,
                "deterministic_score": round(det_score, 4),
                "embedding_score": emb_score,
                "hybrid_score": round(min(hybrid_score, 0.999), 4),
                "inferred_facets": det_item["inferred_facets"] if det_item else [],
                "topic_matched": det_item["topic_matched"] if det_item else False,
                "source_references": [source_ref],
                "reasons": reasons or ["Dense semantic similarity"],
                "retrieval_mode": retrieval_mode,
            }
        )

    fused.sort(key=lambda item: (-item["hybrid_score"], item["obligation_id"]))
    return {
        "candidates": fused[:top_k],
        "all_emb_scores": emb_scores,
        "retrieval_mode": retrieval_mode,
        "fallback_reason": fallback_reason,
    }


def _dimension_precheck_summary(
    clause: EnterpriseClause,
    obligation: AtomicObligation,
) -> Dict[str, Any]:
    """Extract deterministic dimension cues to pass as verifiable context to LLM Stage B."""
    polarity = _detect_action_polarity(clause)
    ent_amounts = _extract_currency_and_amounts(clause.text)
    ent_currency = clause.threshold_currency or (ent_amounts[0][0] if ent_amounts else None)
    ent_threshold = (
        clause.thresholds_aud[0]
        if clause.thresholds_aud
        else (ent_amounts[0][1] if ent_amounts else None)
    )
    ent_operator = clause.threshold_operator or _detect_threshold_operator(clause.text)
    ent_timing = clause.approval_timing or _detect_approval_timing(clause.text)
    ent_actor = clause.required_approval_role or _detect_approval_role(clause.text)
    ent_scopes = _detect_operational_scopes(clause.text)

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

    threshold_comp = "not_applicable"
    if ent_threshold is not None or ext_threshold is not None:
        if ent_currency and ext_currency and ent_currency.upper() != ext_currency.upper():
            threshold_comp = "currency_mismatch"
        elif ent_currency and ent_currency.upper() != "AUD" and obligation.jurisdiction == "AU":
            threshold_comp = "currency_mismatch"
        elif ent_threshold is not None and ext_threshold is not None:
            e_op = ent_operator or ">"
            x_op = ext_operator or ">"
            if abs(ent_threshold - ext_threshold) < 1e-9:
                threshold_comp = "operator_boundary_difference" if e_op != x_op else "identical"
            elif ent_threshold < ext_threshold:
                threshold_comp = "stricter_enterprise"
            else:
                threshold_comp = "weaker_enterprise"

    ent_hours, ext_hours, timeframe_conflict, timeframe_stricter = (
        _compare_obligation_bound_timeframes(clause.text, obligation, ext_text)
    )

    timing_comp = "not_applicable"
    if ent_timing == "post_execution" and ext_timing == "pre_execution":
        timing_comp = "weaker_post_execution"
    elif ent_timing == "pre_execution" and ext_timing in {"post_execution", None}:
        timing_comp = "stricter_pre_execution"

    numerical_thresholds: List[str] = []
    if ent_threshold is not None:
        numerical_thresholds.append(f"{ent_currency or 'AUD'} {ent_operator or ''} {ent_threshold:g}".strip())
    if ent_hours is not None:
        numerical_thresholds.append(f"{ent_hours:g} hours")

    return {
        "enterprise_scope": ",".join(ent_scopes) if ent_scopes else "enterprise_general",
        "enterprise_actor": ent_actor,
        "enterprise_timing": ent_timing,
        "timing_comparison": timing_comp,
        "action_polarity": polarity,
        "threshold_comparison": threshold_comp,
        "timeframe_conflict": timeframe_conflict,
        "timeframe_stricter": timeframe_stricter,
        "has_exception_clause": clause.has_exception_clause,
        "exception_description": clause.exception_description,
        "is_conditional": clause.is_conditional,
        "condition_description": clause.condition_description,
        "is_ambiguous": _is_ambiguous_clause(clause),
        "numerical_thresholds": numerical_thresholds,
    }


def validate_hybrid_candidate_relationship(
    *,
    clause: EnterpriseClause,
    obligation: Optional[AtomicObligation],
    regulatory_pack: RegulatoryPack,
    enterprise_baseline: EnterpriseBaseline,
    policy_version: str,
    policy_name: Optional[str],
    stage_a_reason: str,
    matching_mode: str,
    embedding_similarity: Optional[float] = None,
    semantic_analysis: Optional[SemanticRelationshipAnalysis] = None,
    provider_meta: Optional[Dict[str, Any]] = None,
) -> ReconciliationDecision:
    """Stage C: Authoritative deterministic validation over optional LLM semantic output.

    Preserves strict Stage C veto power:
    - Deterministic validation runs strictly on the unmodified `clause` so LLM-inferred
      facets can NEVER manufacture a false `EQUIVALENT`.
    - If deterministic checks find ambiguity, currency/threshold/operator/timing/actor/
      scope mismatch, waiver exception, conditional narrowing, or negative exemption,
      any LLM claim of `equivalent` is vetoed.
    - When deterministic Stage A/B missed a colloquial paraphrase (`UNMAPPED`) and the LLM
      finds valid semantic alignment without deterministic blockers, Stage C may surface it
      as `partially_overlapping` / `stricter` / `weaker` / `potential_conflict` for human review,
      capped so `EQUIVALENT` still requires deterministic confirmation.
    - `decision_status` NEVER becomes APPROVED automatically.
    """
    base_decision = validate_candidate_relationship(
        clause=clause,
        obligation=obligation,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=enterprise_baseline,
        policy_version=policy_version,
        policy_name=policy_name,
        stage_a_reason=stage_a_reason,
    )
    original_sha = compute_clause_sha256(clause)

    validated_rel = base_decision.validated_relationship
    decision_status = base_decision.decision_status
    proposed_rel = (
        semantic_analysis.proposed_relationship
        if semantic_analysis is not None
        else base_decision.proposed_relationship
    )
    uncertainties = list(base_decision.uncertainties or [])
    supporting_passages = list(base_decision.supporting_passages or [])
    rationale = base_decision.comparison_rationale

    if semantic_analysis is not None:
        if semantic_analysis.supporting_clause_quote not in " ".join(supporting_passages):
            supporting_passages.append(
                f"[Semantic Clause Quote / {clause.clause_id}] {semantic_analysis.supporting_clause_quote}"
            )
        veto_reasons: List[str] = []

        # Allow semantic paraphrase recovery when deterministic Stage B saw UNMAPPED
        # (e.g., colloquial paraphrase lacking canonical keywords), strictly without EQUIVALENT!
        dim_summary = (
            _dimension_precheck_summary(clause, obligation) if obligation is not None else {}
        )
        det_has_blocker = (
            bool(dim_summary.get("is_ambiguous"))
            or dim_summary.get("threshold_comparison") == "currency_mismatch"
        )
        if (
            obligation is not None
            and validated_rel == ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
            and not det_has_blocker
            and semantic_analysis.semantic_relevance in {"high", "medium"}
        ):
            if semantic_analysis.potential_contradiction or proposed_rel == ReconciliationRelationship.POTENTIAL_CONFLICT:
                validated_rel = ReconciliationRelationship.POTENTIAL_CONFLICT
                decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
            elif proposed_rel == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT:
                validated_rel = ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
                decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
            elif proposed_rel == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT:
                validated_rel = ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT
                decision_status = ReconciliationDecisionStatus.PROPOSED
            elif proposed_rel in {
                ReconciliationRelationship.PARTIALLY_OVERLAPPING,
                ReconciliationRelationship.EQUIVALENT,
            }:
                validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
                decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
                if proposed_rel == ReconciliationRelationship.EQUIVALENT:
                    veto_reasons.append(
                        "Stage C capped AI-proposed 'equivalent' to 'partially_overlapping': "
                        "deterministic checks did not establish full canonical facet equivalence."
                    )
        elif (
            validated_rel == ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP
            and proposed_rel == ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT
        ):
            validated_rel = ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT
            decision_status = ReconciliationDecisionStatus.PROPOSED

        # Stage C Deterministic Veto Checks over LLM Stage B claims:
        if (
            proposed_rel == ReconciliationRelationship.EQUIVALENT
            and validated_rel != ReconciliationRelationship.EQUIVALENT
            and not any("capped AI-proposed" in vr for vr in veto_reasons)
        ):
            veto_reasons.append(
                f"Stage C deterministic check vetoed AI-proposed 'equivalent' and enforced '{validated_rel.value}'."
            )
        if validated_rel == ReconciliationRelationship.EQUIVALENT and (
            semantic_analysis.potential_contradiction
            or proposed_rel == ReconciliationRelationship.POTENTIAL_CONFLICT
        ):
            validated_rel = ReconciliationRelationship.POTENTIAL_CONFLICT
            decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
            veto_reasons.append(
                f"Stage C escalated to 'potential_conflict': {semantic_analysis.contradiction_detail or 'semantic contradiction'}."
            )
        elif (
            validated_rel == ReconciliationRelationship.EQUIVALENT
            and proposed_rel == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
        ):
            validated_rel = ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
            decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
            veto_reasons.append(
                "Stage C downgraded deterministic 'equivalent' due to semantic exception/weakening risk."
            )
        elif (
            validated_rel == ReconciliationRelationship.EQUIVALENT
            and semantic_analysis.confidence < 0.75
        ):
            validated_rel = ReconciliationRelationship.PARTIALLY_OVERLAPPING
            decision_status = ReconciliationDecisionStatus.NEEDS_REVIEW
            veto_reasons.append(
                f"Low semantic confidence ({semantic_analysis.confidence:.2f} < 0.75) prevents deterministic 'equivalent'."
            )

        for flag in semantic_analysis.uncertainty_flags:
            if flag and flag not in uncertainties:
                uncertainties.append(flag)
        for vr in veto_reasons:
            if vr not in uncertainties:
                uncertainties.append(vr)

        rationale = (
            f"{base_decision.comparison_rationale} "
            f"[Semantic Interpretation ({semantic_analysis.cited_obligation_id} / "
            f"{semantic_analysis.cited_provision}): {semantic_analysis.reasoning_summary}]"
        )
        if veto_reasons:
            rationale += " " + " ".join(veto_reasons)

    # Ironclad invariant: semantic pipeline NEVER emits APPROVED
    if decision_status == ReconciliationDecisionStatus.APPROVED:
        decision_status = ReconciliationDecisionStatus.PROPOSED

    ai_proposed_rel = (
        semantic_analysis.proposed_relationship if semantic_analysis is not None else None
    )
    veto_list: List[str] = list(veto_reasons) if semantic_analysis is not None else []
    missing_conds = list(base_decision.missing_conditions_or_evidence or [])
    for u in uncertainties:
        if u not in missing_conds:
            missing_conds.append(u)

    preserved_evidence: List[Dict[str, Any]] = list(base_decision.preserved_candidate_evidence or [])
    if obligation is not None and (
        veto_list
        or validated_rel != proposed_rel
        or validated_rel
        in {
            ReconciliationRelationship.PARTIALLY_OVERLAPPING,
            ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
            ReconciliationRelationship.POTENTIAL_CONFLICT,
            ReconciliationRelationship.UNDETERMINED,
        }
    ):
        preserved_evidence.append(
            {
                "obligation_id": obligation.obligation_id,
                "provision": obligation.provision,
                "stage_a_reason": stage_a_reason,
                "embedding_similarity": embedding_similarity,
                "ai_proposed_relationship": ai_proposed_rel.value if ai_proposed_rel else None,
                "deterministically_validated_relationship": validated_rel.value,
                "deterministic_veto_applied": bool(veto_list),
                "deterministic_veto_reasons": veto_list,
                "supporting_passages": supporting_passages,
                "missing_conditions_or_evidence": missing_conds,
            }
        )

    if validated_rel == ReconciliationRelationship.EQUIVALENT:
        rel_state = "equivalent_pending_human_review"
    elif validated_rel == ReconciliationRelationship.POTENTIAL_CONFLICT:
        rel_state = "requirement_apparently_contradicted"
    elif validated_rel in {
        ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
    }:
        rel_state = "requirement_partially_addressed"
    elif validated_rel in {
        ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        ReconciliationRelationship.UNDETERMINED,
    }:
        rel_state = "evidence_insufficient"
    elif validated_rel == ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP:
        rel_state = "no_relevant_requirement_found"
    else:
        rel_state = "requirement_potentially_relevant"

    return base_decision.model_copy(
        update={
            "enterprise_clause_sha256": original_sha,
            "proposed_relationship": proposed_rel,
            "validated_relationship": validated_rel,
            "ai_proposed_relationship": ai_proposed_rel,
            "approved_relationship": None,
            "decision_status": decision_status,
            "supporting_passages": supporting_passages,
            "comparison_rationale": rationale,
            "uncertainties": uncertainties,
            "deterministic_veto_applied": bool(veto_list),
            "deterministic_veto_reasons": veto_list,
            "missing_conditions_or_evidence": missing_conds,
            "candidate_relevance_state": rel_state,
            "preserved_candidate_evidence": preserved_evidence,
            "matching_mode": matching_mode,
            "embedding_similarity": embedding_similarity,
            "semantic_analysis": (
                semantic_analysis.model_dump(mode="json")
                if semantic_analysis is not None
                else None
            ),
            "semantic_provider_meta": provider_meta,
        }
    )


def generate_hybrid_reconciliation_candidates(
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
    config: Optional[LLMRuntimeConfig] = None,
    bundle: Optional[SemanticProviderBundle] = None,
    data_classification: DataClassification = DataClassification.CONFIDENTIAL_ENTERPRISE,
) -> Tuple[List[ReconciliationDecision], Dict[str, Any]]:
    """Run Configuration A, B, or C reconciliation across an EnterpriseBaseline.

    - A (disabled): existing deterministic `generate_reconciliation_candidates`.
    - B (embedding_only): Embedding Stage A retrieval + deterministic Stage C validation.
    - C (hybrid): Embedding Stage A + Schema-validated LLM Stage B + Stage C veto + Stage D Proposed.
    """
    cfg = config or (bundle.config if bundle is not None else LLMRuntimeConfig(semantic_matching_enabled=False))

    if not cfg.semantic_matching_enabled or cfg.matching_mode == SemanticMatchingMode.DISABLED:
        decisions = generate_reconciliation_candidates(
            tenant_id=tenant_id,
            enterprise_baseline=enterprise_baseline,
            regulatory_pack=regulatory_pack,
            policies=policies,
            control_library=control_library,
            obligation_mappings=obligation_mappings,
            use_case=use_case,
            include_non_applicable=include_non_applicable,
            include_proposed_clauses=include_proposed_clauses,
        )
        return decisions, {
            "matching_mode": "deterministic_only",
            "telemetry": (bundle.telemetry.model_dump(mode="json") if bundle else {}),
        }

    if enterprise_baseline.tenant_id != tenant_id:
        raise ValueError("Tenant mismatch when generating reconciliation candidates.")

    enforce_runtime_confidentiality(
        cfg,
        data_classification=data_classification,
        tenant_id=tenant_id,
    )
    active_bundle = bundle or build_provider_bundle(cfg)
    reg_pack = regulatory_pack or load_regulatory_pack()
    ctrl_lib = control_library or load_unified_control_library()
    ob_map_cat = obligation_mappings or load_obligation_control_mappings()

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
    ob_by_id = {ob.obligation_id: ob for ob in candidate_obligations}

    control_to_obligations: Dict[str, List[AtomicObligation]] = {}
    for ob in candidate_obligations:
        if ob.control_id:
            control_to_obligations.setdefault(ob.control_id, []).append(ob)
    for ctrl in ctrl_lib.controls:
        for oid in ctrl.associated_obligation_ids:
            if oid in ob_by_id and all(x.obligation_id != oid for x in control_to_obligations.setdefault(ctrl.control_id, [])):
                control_to_obligations[ctrl.control_id].append(ob_by_id[oid])
    non_eq_rels = {MappingRelationship.NON_EQUIVALENT, MappingRelationship.NOT_EQUIVALENT}
    for m in ob_map_cat.mappings:
        if m.mapping_relationship in non_eq_rels:
            continue
        if m.obligation_id in ob_by_id and all(x.obligation_id != m.obligation_id for x in control_to_obligations.setdefault(m.control_id, [])):
            control_to_obligations[m.control_id].append(ob_by_id[m.obligation_id])

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

    active_clauses: List[EnterpriseClause] = []
    for clause in raw_clauses:
        if clause.policy_id in superseded_policy_ids:
            continue
        if clause.review_status == ClauseReviewStatus.REJECTED:
            continue
        if not include_proposed_clauses and clause.review_status not in {
            ClauseReviewStatus.APPROVED,
            ClauseReviewStatus.CONFIRMED,
        }:
            continue
        active_clauses.append(clause)

    use_llm = (
        cfg.matching_mode == SemanticMatchingMode.HYBRID
        and active_bundle.reasoning_provider is not None
    )
    decisions: List[ReconciliationDecision] = []

    def _is_internal_enterprise_control(c: EnterpriseClause) -> bool:
        low = (c.text or "").lower()
        return bool(c.mandatory) and any(
            cue in low
            for cue in (
                "delegated financial authority",
                "treasury ledger",
                "prompt logging",
                "telemetry vault",
                "worm storage",
                "provenance manifest",
                "build provenance",
                "artifact vault",
                "watermark provenance",
                "internal approval limit",
            )
        )

    for clause in active_clauses:
        pol_version = policy_versions.get(clause.policy_id, enterprise_baseline.version)
        pol_name = policy_names.get(clause.policy_id, clause.source_name)

        # Indeterminate/vague clauses MUST resolve safely to UNDETERMINED while preserving candidate evidence
        if _is_ambiguous_clause(clause):
            mode_label = (
                "hybrid_embedding_llm_deterministic"
                if use_llm
                else "embedding_plus_deterministic"
            )
            preserved_ambig = [
                {
                    "obligation_id": ob.obligation_id,
                    "provision": ob.provision,
                    "reason": topic_reason,
                    "status": "held_pending_unresolved_dependency",
                }
                for ob, topic_reason in _match_topic_obligations_for_unmapped_or_negative_clause(
                    clause, candidate_obligations
                )
            ]
            ambig_dec = validate_hybrid_candidate_relationship(
                clause=clause,
                obligation=None,
                regulatory_pack=reg_pack,
                enterprise_baseline=enterprise_baseline,
                policy_version=pol_version,
                policy_name=pol_name,
                stage_a_reason="Clause contains indeterminate/vague schedule or discretionary reference.",
                matching_mode=mode_label,
                provider_meta={"retrieval_mode": "ambiguous_guardrail"},
            )
            if preserved_ambig:
                ambig_dec = ambig_dec.model_copy(
                    update={"preserved_candidate_evidence": preserved_ambig}
                )
            decisions.append(ambig_dec)
            continue

        non_eq_rels = {MappingRelationship.NON_EQUIVALENT, MappingRelationship.NOT_EQUIVALENT}
        non_rejected_mappings = [
            m
            for m in (clause.control_mappings or [])
            if m.review_status != ClauseReviewStatus.REJECTED
            and m.relationship not in non_eq_rels
        ]
        # Track whether candidate obligations have strong explicit human/statutory provenance
        # vs auto-tagged keyword heuristic mappings emitted on upload.
        explicit_human_controls: Set[str] = {
            m.control_id
            for m in non_rejected_mappings
            if m.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
            and not (m.rationale or "").startswith("Clause contains facet '")
        }
        has_manual_canonical = any(
            f not in ENTERPRISE_GENERIC_FACETS for f in (clause.control_facets or [])
        )
        explicit_citation = _has_explicit_citation(clause.text)

        # Map obligation_id -> (obligation, reasons, emb_score, is_strong, hybrid_score)
        matched: Dict[str, Tuple[AtomicObligation, List[str], Optional[float], bool, float]] = {}

        # Explicit Signal 1 (control mappings)
        for m in non_rejected_mappings:
            is_strong = m.control_id in explicit_human_controls
            for expanded_cid in _expand_control_ids([m.control_id]):
                for ob in control_to_obligations.get(expanded_cid, []):
                    entry = matched.setdefault(ob.obligation_id, (ob, [], None, False, 0.35 if is_strong else 0.18))
                    r = f"Control mapping '{m.control_id}' ({m.review_status.value})"
                    if r not in entry[1]:
                        entry[1].append(r)
                    matched[ob.obligation_id] = (ob, entry[1], entry[2], entry[3] or is_strong, max(entry[4], 0.35 if is_strong else 0.18))

        # Explicit Signal 2 (direct facets)
        clause_facets = set(clause.control_facets or [])
        if clause_facets:
            for ob in candidate_obligations:
                overlap = sorted(clause_facets & set(ob.coverage_facets or []))
                if overlap:
                    entry = matched.setdefault(ob.obligation_id, (ob, [], None, False, 0.40 if has_manual_canonical else 0.25))
                    r = f"Shared coverage facets {overlap}"
                    if r not in entry[1]:
                        entry[1].append(r)
                    matched[ob.obligation_id] = (ob, entry[1], entry[2], entry[3] or has_manual_canonical, max(entry[4], 0.40 if has_manual_canonical else 0.25))

        # Explicit Signal 3 (topic / negative exemption)
        for ob, topic_reason in _match_topic_obligations_for_unmapped_or_negative_clause(
            clause, candidate_obligations
        ):
            entry = matched.setdefault(ob.obligation_id, (ob, [], None, False, 0.35))
            if topic_reason not in entry[1]:
                entry[1].append(topic_reason)
            matched[ob.obligation_id] = (ob, entry[1], entry[2], entry[3] or explicit_citation, max(entry[4], 0.35))

        # Hybrid Stage A retrieval (fuses deterministic ranker + embedding cosine)
        retrieval = retrieve_reconciliation_candidates_hybrid(
            clause,
            regulatory_pack=reg_pack,
            control_library=ctrl_lib,
            obligation_mappings=ob_map_cat,
            use_case=use_case,
            include_non_applicable=include_non_applicable,
            bundle=active_bundle,
            data_classification=data_classification,
            top_k=cfg.top_k_candidates,
        )
        all_emb_scores = retrieval.get("all_emb_scores") or {}
        emb_by_ob = {
            c["obligation_id"]: c.get("embedding_score") for c in retrieval["candidates"]
        }
        for oid_existing, entry in list(matched.items()):
            if entry[2] is None and oid_existing in all_emb_scores:
                matched[oid_existing] = (entry[0], entry[1], all_emb_scores[oid_existing], entry[3], entry[4])

        for cand in retrieval["candidates"]:
            oid = cand["obligation_id"]
            emb_sc = cand.get("embedding_score")
            hyb_sc = cand["hybrid_score"]
            if (
                oid in matched
                or (emb_sc is not None and (emb_sc >= 0.36 or hyb_sc >= 0.36))
                or (emb_sc is None and cand["deterministic_score"] >= 0.30 and (cand["inferred_facets"] or cand["topic_matched"]))
            ):
                ob_cand = cand["obligation"]
                entry = matched.setdefault(ob_cand.obligation_id, (ob_cand, [], emb_sc, False, hyb_sc))
                for r in cand["reasons"]:
                    if r not in entry[1]:
                        entry[1].append(r)
                matched[oid] = (
                    ob_cand,
                    entry[1],
                    emb_sc if emb_sc is not None else entry[2],
                    entry[3],
                    max(entry[4], hyb_sc),
                )

        # Rank selected candidate obligations by fused hybrid_score + strong provenance
        ranked_selected = sorted(
            matched.values(),
            key=lambda item: (
                -item[4],
                -int(item[3]),
                -(item[2] if item[2] is not None else 0.0),
                item[0].obligation_id,
            ),
        )
        # Keep top candidates within call budget while ensuring multi-regulator diversity
        max_cands = min(
            max(cfg.top_k_candidates, 3),
            max(3 if use_llm else 2, len([x for x in ranked_selected if x[3]])),
        )
        candidates_to_validate = list(ranked_selected[:max_cands])
        if len(ranked_selected) > len(candidates_to_validate):
            selected_sources = {item[0].source_id for item in candidates_to_validate}
            for extra_item in ranked_selected[len(candidates_to_validate) :]:
                if (
                    extra_item[0].source_id not in selected_sources
                    and (extra_item[4] >= 0.34 or extra_item[3])
                ):
                    if len(candidates_to_validate) >= max_cands and len(candidates_to_validate) >= 2:
                        # Replace a duplicate-source lower-ranked candidate if present
                        for idx in range(len(candidates_to_validate) - 1, 0, -1):
                            src_i = candidates_to_validate[idx][0].source_id
                            if sum(1 for c_it in candidates_to_validate if c_it[0].source_id == src_i) > 1:
                                candidates_to_validate[idx] = extra_item
                                selected_sources.add(extra_item[0].source_id)
                                break
                    else:
                        candidates_to_validate.append(extra_item)
                        selected_sources.add(extra_item[0].source_id)

        if not candidates_to_validate:
            mode_label = (
                "deterministic_fallback"
                if retrieval["retrieval_mode"] == "deterministic_fallback"
                else (
                    "hybrid_embedding_llm_deterministic"
                    if use_llm
                    else "embedding_plus_deterministic"
                )
            )
            standalone = validate_hybrid_candidate_relationship(
                clause=clause,
                obligation=None,
                regulatory_pack=reg_pack,
                enterprise_baseline=enterprise_baseline,
                policy_version=pol_version,
                policy_name=pol_name,
                stage_a_reason="No external obligation exceeded hybrid retrieval thresholds.",
                matching_mode=mode_label,
                provider_meta={"retrieval_mode": retrieval["retrieval_mode"]},
            )
            if _is_internal_enterprise_control(clause):
                standalone = standalone.model_copy(
                    update={
                        "proposed_relationship": ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
                        "validated_relationship": ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
                    }
                )
            decisions.append(standalone)
            continue

        # Run Stage B LLM Semantic Interpretation on candidates if enabled
        interpreted: List[
            Tuple[AtomicObligation, List[str], Optional[float], bool, Optional[SemanticRelationshipAnalysis], Optional[str], float]
        ] = []
        for ob, reasons, emb_sc, is_strong, hyb_sc in candidates_to_validate:
            sem_analysis: Optional[SemanticRelationshipAnalysis] = None
            llm_err: Optional[str] = None
            if use_llm and active_bundle.reasoning_provider is not None:
                dim_precheck = _dimension_precheck_summary(clause, ob)
                try:
                    sem_analysis = active_bundle.reasoning_provider.analyze_reconciliation(
                        clause_id=clause.clause_id,
                        clause_text=clause.text,
                        obligation=ob,
                        dimension_summary=dim_precheck,
                        data_classification=data_classification,
                        tenant_id=tenant_id,
                    )
                    # Defense-in-depth citation re-check at integration layer
                    validate_semantic_citation(sem_analysis, source_text=clause.text, obligation=ob)
                except (ConfidentialityPolicyError, ProviderConfigurationError):
                    raise
                except CitationVerificationError as exc:
                    active_bundle.telemetry.citation_rejections += 1
                    active_bundle.telemetry.fallback_events += 1
                    llm_err = f"Rejected ungrounded LLM citation: {scrub_secrets(str(exc))}"
                except LLMProviderError as exc:
                    active_bundle.telemetry.fallback_events += 1
                    llm_err = f"LLM fallback to deterministic Stage B: {scrub_secrets(str(exc))}"
            interpreted.append((ob, reasons, emb_sc, is_strong, sem_analysis, llm_err, hyb_sc))

        # Suppress noisy false positives ONLY when LLM confirms ALL candidates have semantic_relevance="none"
        # AND deterministic validation itself does NOT find a substantive conflict/stricter/weaker/equivalent match!
        det_preserves_candidate = False
        if interpreted and not explicit_citation and not has_manual_canonical:
            for item_ob, item_reasons, _emb_sc, item_strong, _sem, _err, _hyb in interpreted:
                if item_strong:
                    det_preserves_candidate = True
                    break
                det_chk = validate_candidate_relationship(
                    clause=clause,
                    obligation=item_ob,
                    regulatory_pack=reg_pack,
                    enterprise_baseline=enterprise_baseline,
                    policy_version=pol_version,
                    policy_name=pol_name,
                    stage_a_reason="; ".join(item_reasons),
                )
                if det_chk.validated_relationship in {
                    ReconciliationRelationship.EQUIVALENT,
                    ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
                    ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
                    ReconciliationRelationship.POTENTIAL_CONFLICT,
                    ReconciliationRelationship.UNDETERMINED,
                }:
                    det_preserves_candidate = True
                    break

        if (
            use_llm
            and interpreted
            and not explicit_citation
            and not has_manual_canonical
            and not det_preserves_candidate
            and all(item[4] is not None and item[4].semantic_relevance == "none" for item in interpreted)
        ):
            dismissed_notes = [
                f"Candidate '{item[0].obligation_id}' dismissed by semantic interpretation (semantic_relevance='none': {item[4].reasoning_summary})."
                for item in interpreted
                if item[4] is not None
            ]
            top_sem = interpreted[0][4]
            standalone = validate_hybrid_candidate_relationship(
                clause=clause,
                obligation=None,
                regulatory_pack=reg_pack,
                enterprise_baseline=enterprise_baseline,
                policy_version=pol_version,
                policy_name=pol_name,
                stage_a_reason="; ".join(dismissed_notes),
                matching_mode="hybrid_embedding_llm_deterministic",
                provider_meta={
                    "retrieval_mode": retrieval["retrieval_mode"],
                    "dismissed_candidate_ids": [item[0].obligation_id for item in interpreted],
                },
            )
            if top_sem and top_sem.proposed_relationship in {
                ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
                ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
            }:
                standalone = standalone.model_copy(
                    update={
                        "proposed_relationship": top_sem.proposed_relationship,
                        "validated_relationship": top_sem.proposed_relationship,
                        "uncertainties": list(standalone.uncertainties) + dismissed_notes,
                    }
                )
            standalone = standalone.model_copy(
                update={
                    "candidate_relevance_state": "irrelevant_candidate_dismissed",
                    "preserved_candidate_evidence": [
                        {
                            "obligation_id": item[0].obligation_id,
                            "provision": item[0].provision,
                            "embedding_similarity": item[2],
                            "semantic_relevance": item[4].semantic_relevance if item[4] else None,
                            "ai_proposed_relationship": (
                                item[4].proposed_relationship.value if item[4] else None
                            ),
                            "dismissal_reason": item[4].reasoning_summary if item[4] else "Low relevance",
                        }
                        for item in interpreted
                    ],
                }
            )
            decisions.append(standalone)
            continue

        # Sort so highest-relevance / confidence / hybrid score candidate appears first for the clause
        interpreted.sort(
            key=lambda item: (
                {"high": 3, "medium": 2, "low": 1, "none": 0}.get(
                    item[4].semantic_relevance if item[4] else "low", 1
                ),
                item[4].confidence if item[4] else 0.0,
                item[6],
                item[2] if item[2] is not None else 0.0,
            ),
            reverse=True,
        )

        # If at least one candidate has high/medium semantic relevance, drop unrelated `none` candidates
        # unless deterministic checks hold a strong link OR deterministic Stage C validation finds
        # a substantive statutory relationship (preventing Stage B from silently erasing a valid match).
        has_substantive_sem = any(
            item[4] is not None and item[4].semantic_relevance in {"high", "medium"}
            for item in interpreted
        )
        if has_substantive_sem:
            filtered = []
            for item in interpreted:
                keep = item[3] or item[4] is None or item[4].semantic_relevance != "none"
                if not keep:
                    det_chk = validate_candidate_relationship(
                        clause=clause,
                        obligation=item[0],
                        regulatory_pack=reg_pack,
                        enterprise_baseline=enterprise_baseline,
                        policy_version=pol_version,
                        policy_name=pol_name,
                        stage_a_reason="; ".join(item[1]),
                    )
                    if det_chk.validated_relationship in {
                        ReconciliationRelationship.EQUIVALENT,
                        ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
                        ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
                        ReconciliationRelationship.POTENTIAL_CONFLICT,
                    }:
                        keep = True
                if keep:
                    filtered.append(item)
            if filtered:
                interpreted = filtered

        for ob, reasons, emb_sc, _is_strong, sem_analysis, llm_err, _hyb in interpreted:
            if retrieval["retrieval_mode"] == "deterministic_fallback" or llm_err is not None:
                mode_label = "deterministic_fallback"
            elif use_llm and sem_analysis is not None:
                mode_label = "hybrid_embedding_llm_deterministic"
            elif emb_sc is not None:
                mode_label = "embedding_plus_deterministic"
            else:
                mode_label = "deterministic_only"

            dec = validate_hybrid_candidate_relationship(
                clause=clause,
                obligation=ob,
                regulatory_pack=reg_pack,
                enterprise_baseline=enterprise_baseline,
                policy_version=pol_version,
                policy_name=pol_name,
                stage_a_reason="; ".join(reasons),
                matching_mode=mode_label,
                embedding_similarity=emb_sc if emb_sc is not None else emb_by_ob.get(ob.obligation_id),
                semantic_analysis=sem_analysis,
                provider_meta={
                    "retrieval_mode": retrieval["retrieval_mode"],
                    "reasoning_model": (
                        active_bundle.reasoning_provider.model_name
                        if active_bundle.reasoning_provider
                        else None
                    ),
                    "fallback_note": llm_err or retrieval["fallback_reason"],
                },
            )
            if llm_err:
                dec = dec.model_copy(update={"uncertainties": [*dec.uncertainties, llm_err]})
            decisions.append(dec)

    decisions.extend(
        _detect_internal_enterprise_conflicts(
            active_clauses,
            enterprise_baseline=enterprise_baseline,
            regulatory_pack=reg_pack,
            policy_versions=policy_versions,
        )
    )

    return decisions, {
        "matching_mode": cfg.matching_mode.value,
        "telemetry": active_bundle.telemetry.model_dump(mode="json"),
    }


def suggest_questionnaire_mappings_hybrid(
    *,
    question_bank: QuestionBank,
    regulatory_pack: Optional[RegulatoryPack] = None,
    use_case: Optional[BankingUseCase] = None,
    bundle: Optional[SemanticProviderBundle] = None,
    tenant_id: str = "default",
    data_classification: DataClassification = DataClassification.CONFIDENTIAL_ENTERPRISE,
    top_k_per_question: int = 3,
) -> Tuple[List[MappingDecision], Dict[str, Any]]:
    """Section 7 Harness: Suggest PROPOSED questionnaire-to-obligation MappingDecisions.

    Strictly returns `review_status=ReviewStatus.PROPOSED`. Never alters or replaces
    the production Questionnaire Coverage Engine and never produces confirmed coverage.
    """
    resolved_tenant = getattr(question_bank.metadata, "tenant_id", None) or tenant_id
    q_sha = getattr(question_bank.metadata, "source_sha256", None) or getattr(
        question_bank.metadata, "workbook_sha256", None
    )
    reg_pack = regulatory_pack or load_regulatory_pack()
    applicable_obs = list(reg_pack.obligations)
    if use_case is not None:
        app_decisions = select_applicable_obligations(reg_pack.obligations, use_case)
        app_ids = {
            d.obligation_id
            for d in app_decisions
            if d.status
            in {
                ApplicabilityStatus.APPLICABLE,
                ApplicabilityStatus.CONDITIONAL,
                ApplicabilityStatus.UNDETERMINED,
            }
        }
        applicable_obs = [ob for ob in reg_pack.obligations if ob.obligation_id in app_ids]

    ob_texts = [_format_obligation_embedding_text(ob) for ob in applicable_obs]
    ob_vecs: Optional[List[List[float]]] = None
    if (
        bundle is not None
        and bundle.config.semantic_matching_enabled
        and bundle.embedding_provider is not None
        and bundle.embedding_provider.supports_embeddings
        and applicable_obs
    ):
        enforce_runtime_confidentiality(
            bundle.config,
            data_classification=data_classification,
            tenant_id=resolved_tenant,
        )
        try:
            ob_vecs = bundle.embed_with_cache(
                ob_texts,
                task_type="RETRIEVAL_DOCUMENT",
                data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
                tenant_id=resolved_tenant,
            )
        except (ConfidentialityPolicyError, ProviderConfigurationError):
            raise
        except LLMProviderError as exc:
            bundle.telemetry.fallback_events += 1
            bundle.telemetry.notes.append(
                f"Questionnaire embedding fallback: {scrub_secrets(str(exc))}"
            )

    decisions: List[MappingDecision] = []
    q_rank_telemetry: Dict[str, List[str]] = {}

    for q in question_bank.questions:
        q_prompt = getattr(q, "question_text", None) or getattr(q, "prompt", "") or ""
        q_dom = getattr(q, "risk_domain", None) or getattr(q, "domain", "") or ""
        q_resp = getattr(q, "response", None) or " ".join(getattr(q, "response_tags", []) or [])
        q_text = f"{q_prompt} {q_dom} {q_resp}".strip()
        q_toks = _policy_tokens(q_text)

        scored: List[Tuple[float, AtomicObligation]] = []
        q_vec: Optional[List[float]] = None
        if ob_vecs is not None and bundle is not None:
            try:
                q_vec = bundle.embed_with_cache(
                    [q_text],
                    task_type="RETRIEVAL_QUERY",
                    data_classification=data_classification,
                    tenant_id=resolved_tenant,
                )[0]
            except LLMProviderError as exc:
                bundle.telemetry.fallback_events += 1
                bundle.telemetry.notes.append(
                    f"Question query embedding fallback: {scrub_secrets(str(exc))}"
                )

        for idx, ob in enumerate(applicable_obs):
            ob_toks = _policy_tokens(f"{ob.title} {ob.concise_obligation_summary} {' '.join(ob.coverage_facets)}")
            lex_overlap = len(q_toks & ob_toks) / max(len(ob_toks), 1)
            if q_vec is not None and ob_vecs is not None:
                sim = max(0.0, _cosine_similarity(q_vec, ob_vecs[idx]))
                combined = 0.65 * sim + 0.35 * min(1.0, lex_overlap * 2.0)
            else:
                combined = min(1.0, lex_overlap * 2.0)
            scored.append((combined, ob))

        scored.sort(key=lambda item: (-item[0], item[1].obligation_id))
        top_cands = scored[:top_k_per_question]
        q_rank_telemetry[q.question_id] = [ob.obligation_id for _, ob in top_cands]

        for score, ob in top_cands:
            if score < 0.25:
                continue
            cand_facets: List[str] = []
            conf = round(min(0.95, score), 3)
            reason = f"Semantic retrieval score={score:.3f} (proposed candidate only)."

            if (
                bundle is not None
                and bundle.config.matching_mode == SemanticMatchingMode.HYBRID
                and bundle.reasoning_provider is not None
            ):
                try:
                    sem_q = bundle.reasoning_provider.analyze_questionnaire_match(
                        question_id=q.question_id,
                        question_text=q_text,
                        obligation=ob,
                        data_classification=data_classification,
                        tenant_id=resolved_tenant,
                    )
                    validate_semantic_citation(sem_q, source_text=q_text, obligation=ob)
                    cand_facets = [
                        f for f in sem_q.candidate_covered_facets if f in (ob.coverage_facets or [])
                    ]
                    conf = sem_q.confidence
                    reason = f"Semantic LLM candidate ({sem_q.cited_provision}): {sem_q.reasoning_summary}"
                except LLMProviderError as exc:
                    bundle.telemetry.fallback_events += 1
                    reason += f" [Fallback: {scrub_secrets(str(exc))}]"

            target_facets = cand_facets or (ob.coverage_facets[:1] if ob.coverage_facets else [])
            for facet in target_facets:
                decisions.append(
                    MappingDecision(
                        obligation_id=ob.obligation_id,
                        facet=facet,
                        question_id=q.question_id,
                        review_status=ReviewStatus.PROPOSED,
                        confidence=conf,
                        reason=reason,
                        source_reference=f"{ob.source_id} ({ob.provision})",
                        questionnaire_id=question_bank.metadata.questionnaire_id,
                        questionnaire_sha256=q_sha,
                        regulatory_pack_id=reg_pack.pack_id,
                        regulatory_pack_version=reg_pack.version,
                        control_id=ob.control_id,
                    )
                )

    return decisions, {
        "question_rankings": q_rank_telemetry,
        "telemetry": bundle.telemetry.model_dump(mode="json") if bundle else {},
    }
