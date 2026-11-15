"""Reusable Evaluation Harness for E3 / E3.1 Deterministic, Embedding & Live Gemini Benchmarks.

Computes split-separated (Dev vs Locked Holdout) evaluation metrics with 95% Wilson
confidence intervals, per-phenomenon breakdowns, multi-obligation recall, safety checks
(zero confirmed coverage inflation, false equivalence, false conflict), citation verification,
and API usage / token / rate-limit telemetry.

Synthetic benchmark clauses always execute under `DataClassification.PUBLIC_OR_SYNTHETIC`
so live Gemini free-tier calibration works without relaxing `CONFIDENTIAL_ENTERPRISE`
protections.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..catalog import load_regulatory_pack
from ..coverage import evaluate_questionnaire_coverage
from ..models import (
    BankingUseCase,
    QuestionBank,
    QuestionnaireMetadata,
    QuestionRecord,
    ReviewStatus,
)
from ..policy import compile_enterprise_baseline, extract_enterprise_policy
from ..policy_documents import extract_policy_file
from ..reconciliation import (
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
)
from ..semantic_reconciliation import (
    generate_hybrid_reconciliation_candidates,
    retrieve_reconciliation_candidates_hybrid,
    suggest_questionnaire_mappings_hybrid,
)
from .providers import (
    HttpGetTransport,
    HttpJsonTransport,
    SemanticProviderBundle,
    build_provider_bundle,
    default_urllib_json_get_transport,
    default_urllib_json_transport,
    probe_gemini_model_availability,
)
from .security import scrub_secrets
from .types import (
    DataClassification,
    DeploymentEdition,
    LLMProviderKind,
    LLMRuntimeConfig,
    ProviderConfigurationError,
    SemanticMatchingMode,
)


def wilson_ci_95(hits: int, total: int) -> Tuple[float, float]:
    """Return 95% Wilson score confidence interval (lower, upper) in [0.0, 1.0]."""
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = hits / total
    denom = 1.0 + (z * z) / total
    centre = p + (z * z) / (2.0 * total)
    half = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)
    return (max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom))


def format_metric_ci(hits: int, total: int) -> str:
    if total <= 0:
        return "0/0 (N/A)"
    lo, hi = wilson_ci_95(hits, total)
    return f"{hits}/{total} ({hits / total * 100:.2f}%, 95% CI [{lo * 100:.2f}%, {hi * 100:.2f}%])"


def macro_weighted_prf(y_true: Sequence[str], y_pred: Sequence[str]) -> Dict[str, float]:
    """Compute macro P/R/F1 and weighted F1 over observed ground-truth labels."""
    labels = sorted(set(y_true) | set(y_pred))
    true_labels = sorted(set(y_true))
    if not labels or not y_true:
        return {"macro_p": 0.0, "macro_r": 0.0, "macro_f1": 0.0, "weighted_f1": 0.0}

    per_label_p: List[float] = []
    per_label_r: List[float] = []
    per_label_f1: List[float] = []
    weighted_sum = 0.0
    n = len(y_true)

    for lbl in true_labels:
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == lbl and yp == lbl)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != lbl and yp == lbl)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == lbl and yp != lbl)
        support = tp + fn
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / support if support > 0 else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_label_p.append(p)
        per_label_r.append(r)
        per_label_f1.append(f1)
        weighted_sum += support * f1

    return {
        "macro_p": sum(per_label_p) / len(true_labels),
        "macro_r": sum(per_label_r) / len(true_labels),
        "macro_f1": sum(per_label_f1) / len(true_labels),
        "weighted_f1": weighted_sum / n,
    }


def _default_text_bytes(paragraphs: Sequence[str], _fmt: str, _title: str) -> Tuple[str, bytes]:
    return "txt", ("\n\n".join(paragraphs)).encode("utf-8")


def build_eval_runtime_config(
    *,
    mode: SemanticMatchingMode,
    provider: str = "mock",
    gemini_api_key: Optional[str] = None,
    gemini_billing_tier: str = "free",
    gemini_embedding_model: str = "gemini-embedding-001",
    gemini_reasoning_model: str = "gemini-2.5-flash",
    rpm_min_interval_seconds: float = 0.0,
    max_calls_per_run: int = 1000,
    max_calls_per_minute: int = 600,
) -> LLMRuntimeConfig:
    """Construct validated LLMRuntimeConfig for benchmark evaluation."""
    if mode == SemanticMatchingMode.DISABLED or provider == "disabled":
        return LLMRuntimeConfig(
            edition=DeploymentEdition.SELF_HOSTED,
            semantic_matching_enabled=False,
            matching_mode=SemanticMatchingMode.DISABLED,
            embedding_provider=LLMProviderKind.DISABLED,
            reasoning_provider=LLMProviderKind.DISABLED,
            gemini_billing_tier="paid" if gemini_billing_tier == "paid" else "free",
            gemini_embedding_model=gemini_embedding_model,
            gemini_reasoning_model=gemini_reasoning_model,
        )

    prov_kind = LLMProviderKind.GEMINI if provider == "gemini" else LLMProviderKind.MOCK
    rsn_kind = prov_kind if mode == SemanticMatchingMode.HYBRID else LLMProviderKind.DISABLED

    if prov_kind == LLMProviderKind.GEMINI and not (gemini_api_key or "").strip():
        raise ProviderConfigurationError(
            "GEMINI_API_KEY is required when running live Gemini evaluation (--provider gemini)."
        )

    return LLMRuntimeConfig(
        edition=DeploymentEdition.SELF_HOSTED,
        semantic_matching_enabled=True,
        matching_mode=mode,
        embedding_provider=prov_kind,
        reasoning_provider=rsn_kind,
        gemini_api_key=gemini_api_key,
        gemini_billing_tier="paid" if gemini_billing_tier == "paid" else "free",
        allow_confidential_on_free_tier=False,
        gemini_embedding_model=gemini_embedding_model,
        gemini_reasoning_model=gemini_reasoning_model,
        rpm_min_interval_seconds=rpm_min_interval_seconds,
        max_calls_per_run=min(max(max_calls_per_run, 1), 2000),
        max_calls_per_minute=min(max(max_calls_per_minute, 1), 600),
    )


def evaluate_clause_benchmark(
    clauses: Sequence[Any],
    *,
    mode: SemanticMatchingMode,
    provider: str = "mock",
    config: Optional[LLMRuntimeConfig] = None,
    bundle: Optional[SemanticProviderBundle] = None,
    transport: HttpJsonTransport = default_urllib_json_transport,
    doc_bytes_builder: Optional[Callable[[Sequence[str], str, str], bytes]] = None,
) -> Dict[str, Any]:
    """Run Config A/B/C evaluation across labelled synthetic benchmark clauses."""
    reg_pack = load_regulatory_pack()
    t0_total = time.perf_counter()

    cfg = config or build_eval_runtime_config(mode=mode, provider=provider)
    active_bundle = bundle or build_provider_bundle(cfg, transport=transport)

    org_order: List[str] = []
    for c in clauses:
        if c.org_id not in org_order:
            org_order.append(c.org_id)

    retrieval_queries = 0
    r1_hits = 0
    r5_hits = 0
    multi_ob_total = 0
    multi_ob_retrieval_hits = 0
    multi_ob_decision_hits = 0
    exact_matches = 0
    false_equiv = 0
    false_conflict = 0
    false_cov = 0
    human_total = 0
    human_flagged = 0
    citation_ok = 0
    y_true: List[str] = []
    y_pred: List[str] = []
    per_case: List[Dict[str, Any]] = []
    by_phenomenon: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})

    for org_id in org_order:
        tenant_id = f"eval-{org_id}"
        doc_groups: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
        for c in clauses:
            if c.org_id == org_id:
                doc_groups[(c.doc_filename, c.doc_format)].append(c)

        policies = []
        extracted_by_case_id: Dict[str, Any] = {}
        top_ids_by_case_id: Dict[str, List[str]] = {}
        for (fname, fmt), doc_cases in doc_groups.items():
            paras = [dc.raw_text for dc in doc_cases]
            if doc_bytes_builder is not None and fmt in {"pdf", "docx"}:
                raw = doc_bytes_builder(paras, fmt, f"{org_id} {fname}")
                effective_fname = fname
            else:
                raw = ("\n\n".join(paras)).encode("utf-8")
                effective_fname = fname if fmt == "txt" else f"{fname}.txt"

            extracted_text = extract_policy_file(effective_fname, raw)
            pol = extract_enterprise_policy(
                tenant_id=tenant_id,
                name=fname,
                text=extracted_text,
                created_by="eval-harness",
            )
            approved_clauses = []
            for ext in pol.clauses:
                ext_mappings = [
                    m.model_copy(update={"review_status": ReviewStatus.APPROVED})
                    for m in (ext.control_mappings or [])
                ]
                approved_clauses.append(
                    ext.model_copy(
                        update={
                            "review_status": "approved",
                            "control_mappings": ext_mappings,
                        }
                    )
                )
            pol = pol.model_copy(update={"clauses": approved_clauses})
            policies.append(pol)

            for case in doc_cases:
                norm_full = " ".join(case.raw_text.lower().split())
                matched = next(
                    (c for c in pol.clauses if " ".join(c.text.lower().split()) == norm_full),
                    None,
                )
                if matched is None:
                    matched = next(
                        (c for c in pol.clauses if norm_full in " ".join(c.text.lower().split())),
                        None,
                    )
                if matched is None:
                    raise RuntimeError(f"Extraction failed to isolate benchmark clause {case.case_id}")
                extracted_by_case_id[case.case_id] = matched

                if case.ground_truth_obligation_id is not None:
                    retrieval_queries += 1
                    if cfg.matching_mode == SemanticMatchingMode.DISABLED:
                        ranked = rank_reconciliation_candidates_for_clause(
                            matched,
                            regulatory_pack=reg_pack,
                            top_k=5,
                        )
                        top_ids = [r["obligation_id"] for r in ranked]
                    else:
                        ret = retrieve_reconciliation_candidates_hybrid(
                            matched,
                            regulatory_pack=reg_pack,
                            bundle=active_bundle,
                            data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
                            top_k=5,
                        )
                        top_ids = [r["obligation_id"] for r in ret["candidates"]]
                    top_ids_by_case_id[case.case_id] = top_ids
                    if top_ids and top_ids[0] == case.ground_truth_obligation_id:
                        r1_hits += 1
                    if case.ground_truth_obligation_id in top_ids[:5]:
                        r5_hits += 1

        baseline = compile_enterprise_baseline(
            tenant_id=tenant_id,
            name=f"{org_id} Eval Baseline",
            policies=policies,
            created_by="eval-harness",
        )

        if cfg.matching_mode == SemanticMatchingMode.DISABLED:
            decs = generate_reconciliation_candidates(
                tenant_id=tenant_id,
                enterprise_baseline=baseline,
                policies=policies,
                regulatory_pack=reg_pack,
            )
        else:
            decs, _meta = generate_hybrid_reconciliation_candidates(
                tenant_id=tenant_id,
                enterprise_baseline=baseline,
                policies=policies,
                regulatory_pack=reg_pack,
                config=cfg,
                bundle=active_bundle,
                data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
            )

        for case in [c for c in clauses if c.org_id == org_id]:
            ext_cls = extracted_by_case_id[case.case_id]
            clause_decs = [
                d
                for d in decs
                if d.enterprise_clause_id == ext_cls.clause_id and d.peer_enterprise_clause_id is None
            ]
            chosen = None
            if case.ground_truth_obligation_id is not None:
                chosen = next(
                    (d for d in clause_decs if d.external_obligation_id == case.ground_truth_obligation_id),
                    None,
                )
            if chosen is None and clause_decs:
                chosen = clause_decs[0]
            if chosen is None:
                raise RuntimeError(f"Reconciliation produced zero decisions for {case.case_id}")

            pred_rel = chosen.validated_relationship.value
            true_rel = case.ground_truth_relationship.value
            y_true.append(true_rel)
            y_pred.append(pred_rel)
            is_correct = pred_rel == true_rel
            if is_correct:
                exact_matches += 1
            by_phenomenon[case.phenomenon]["total"] += 1
            if is_correct:
                by_phenomenon[case.phenomenon]["correct"] += 1

            if pred_rel == "equivalent" and true_rel != "equivalent":
                false_equiv += 1
            if pred_rel == "potential_conflict" and true_rel != "potential_conflict":
                false_conflict += 1
            if str(chosen.decision_status.value) == "approved":
                false_cov += 1

            expected_multi = tuple(getattr(case, "expected_obligation_ids", ()) or ())
            multi_ret_ok: Optional[bool] = None
            multi_dec_ok: Optional[bool] = None
            if len(expected_multi) > 1:
                multi_ob_total += 1
                top_ids = top_ids_by_case_id.get(case.case_id, [])
                dec_obs = {d.external_obligation_id for d in clause_decs if d.external_obligation_id}
                multi_ret_ok = all(oid in top_ids for oid in expected_multi)
                multi_dec_ok = all(oid in dec_obs for oid in expected_multi)
                if multi_ret_ok:
                    multi_ob_retrieval_hits += 1
                if multi_dec_ok:
                    multi_ob_decision_hits += 1

            is_flagged = chosen.decision_status.value in {"needs_review", "proposed"} and (
                pred_rel
                in {
                    "potential_conflict",
                    "weaker_or_potentially_insufficient",
                    "undetermined",
                    "unmapped_no_reliable_relationship",
                }
                or bool(chosen.uncertainties)
            )
            if case.expects_human_resolution:
                human_total += 1
                if is_flagged:
                    human_flagged += 1

            has_valid_cit = (
                chosen.enterprise_clause_id == ext_cls.clause_id
                and chosen.enterprise_baseline_id == baseline.baseline_id
                and len(chosen.supporting_passages or []) >= 1
                and (not chosen.external_obligation_id or bool(chosen.external_provision))
            )
            if chosen.semantic_analysis is not None:
                has_valid_cit = has_valid_cit and (
                    chosen.semantic_analysis.get("cited_obligation_id") == chosen.external_obligation_id
                )
            if has_valid_cit:
                citation_ok += 1

            per_case.append(
                {
                    "case_id": case.case_id,
                    "split": case.split,
                    "phenomenon": case.phenomenon,
                    "true_ob": case.ground_truth_obligation_id,
                    "pred_ob": chosen.external_obligation_id,
                    "emitted_obligations": [d.external_obligation_id for d in clause_decs if d.external_obligation_id],
                    "true_rel": true_rel,
                    "pred_rel": pred_rel,
                    "correct": is_correct,
                    "multi_ret_ok": multi_ret_ok,
                    "multi_dec_ok": multi_dec_ok,
                }
            )

    elapsed_ms = (time.perf_counter() - t0_total) * 1000.0
    n = len(clauses)
    prf = macro_weighted_prf(y_true, y_pred)
    tel = active_bundle.telemetry

    return {
        "mode": cfg.matching_mode.value,
        "provider": cfg.reasoning_provider.value if cfg.reasoning_provider != LLMProviderKind.DISABLED else cfg.embedding_provider.value,
        "embedding_model": tel.embedding_model,
        "reasoning_model": tel.reasoning_model,
        "n_clauses": n,
        "retrieval_queries": retrieval_queries,
        "recall_at_1": r1_hits,
        "recall_at_5": r5_hits,
        "multi_ob_total": multi_ob_total,
        "multi_ob_retrieval_hits": multi_ob_retrieval_hits,
        "multi_ob_decision_hits": multi_ob_decision_hits,
        "exact_accuracy": exact_matches,
        "false_equivalence": false_equiv,
        "false_coverage": false_cov,
        "false_conflict": false_conflict,
        "unresolved_flagged": human_flagged,
        "unresolved_total": human_total,
        "citation_accurate": citation_ok,
        "macro_p": round(prf["macro_p"], 4),
        "macro_r": round(prf["macro_r"], 4),
        "macro_f1": round(prf["macro_f1"], 4),
        "weighted_f1": round(prf["weighted_f1"], 4),
        "elapsed_ms": round(elapsed_ms, 2),
        "telemetry": {
            "embedding_calls": tel.embedding_calls,
            "embedding_texts": tel.embedding_texts,
            "embedding_cache_hits": tel.embedding_cache_hits,
            "reasoning_calls": tel.reasoning_calls,
            "api_attempts": tel.api_attempts,
            "prompt_tokens": tel.prompt_tokens,
            "completion_tokens": tel.completion_tokens,
            "thoughts_tokens": tel.thoughts_tokens,
            "total_tokens": tel.total_tokens,
            "estimated_cost_usd": tel.estimated_cost_usd,
            "quota_or_rate_limit_errors": tel.quota_or_rate_limit_errors,
            "citation_rejections": tel.citation_rejections,
            "fallback_events": tel.fallback_events,
            "lifecycle_warnings": [w.model_dump(mode="json") for w in tel.lifecycle_warnings],
        },
        "by_phenomenon": dict(by_phenomenon),
        "per_case": per_case,
    }


def evaluate_questionnaire_benchmark(
    q_cases: Sequence[Any],
    *,
    mode: SemanticMatchingMode,
    provider: str = "mock",
    config: Optional[LLMRuntimeConfig] = None,
    transport: HttpJsonTransport = default_urllib_json_transport,
) -> Dict[str, Any]:
    """Run Section 7 questionnaire-to-obligation evaluation cleanly without altering production coverage."""
    reg_pack = load_regulatory_pack()
    questions = [
        QuestionRecord(
            question_id=q.question_id,
            question_text=f"{q.prompt} {q.response}".strip(),
            risk_domain=q.domain,
            response_tags=["Yes"] if q.response else [],
            source_version="E3-BENCH-1.0",
            source_sheet="E3_Assurance",
        )
        for q in q_cases
    ]
    qb = QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id="E3-Q-BENCH",
            source_filename="e3_q_bench.xlsx",
            source_sha256="a" * 64,
            source_version="E3-BENCH-1.0",
        ),
        questions=questions,
    )
    use_case = BankingUseCase(
        name="Retail Credit & AI Advisory Assistant",
        entity_type="ADI",
        apra_regulated=True,
        handles_personal_information=True,
        handles_sensitive_information=True,
        cross_border_disclosure=True,
        makes_or_assists_significant_decisions=True,
        handles_regulated_complaints=True,
        afs_licensee=True,
        credit_licensee_or_credit_activity=True,
        assists_consumer_credit_decision=True,
        third_party_ai_service=True,
        supports_critical_operation=True,
    )
    cfg = config or build_eval_runtime_config(mode=mode, provider=provider)
    bundle = build_provider_bundle(cfg, transport=transport)
    t0 = time.perf_counter()
    decs, meta = suggest_questionnaire_mappings_hybrid(
        question_bank=qb,
        regulatory_pack=reg_pack,
        use_case=use_case,
        bundle=bundle,
        tenant_id="eval-questionnaire",
        data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
        top_k_per_question=3,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    cov = evaluate_questionnaire_coverage(
        tenant_id="eval-questionnaire",
        use_case=use_case,
        question_bank=qb,
        regulatory_pack=reg_pack,
        review_mappings=decs,
    )
    rankings = meta.get("question_rankings") or {}
    r1_dev = r3_dev = q_dev = 0
    r1_ho = r3_ho = q_ho = 0
    for item in q_cases:
        if item.ground_truth_obligation_id is None:
            continue
        top_ids = rankings.get(item.question_id, [])
        h1 = int(bool(top_ids) and top_ids[0] == item.ground_truth_obligation_id)
        h3 = int(item.ground_truth_obligation_id in top_ids[:3])
        if item.split == "dev":
            q_dev += 1
            r1_dev += h1
            r3_dev += h3
        else:
            q_ho += 1
            r1_ho += h1
            r3_ho += h3
    tel = bundle.telemetry
    return {
        "mode": mode.value,
        "dev_r1": r1_dev,
        "dev_r3": r3_dev,
        "dev_total": q_dev,
        "ho_r1": r1_ho,
        "ho_r3": r3_ho,
        "ho_total": q_ho,
        "combined_r1": r1_dev + r1_ho,
        "combined_r3": r3_dev + r3_ho,
        "combined_total": q_dev + q_ho,
        "confirmed_covered": cov.metrics.confirmed_covered,
        "all_proposed": all(d.review_status == ReviewStatus.PROPOSED for d in decs),
        "elapsed_ms": round(elapsed_ms, 2),
        "telemetry": {
            "embedding_calls": tel.embedding_calls,
            "reasoning_calls": tel.reasoning_calls,
            "prompt_tokens": tel.prompt_tokens,
            "completion_tokens": tel.completion_tokens,
            "thoughts_tokens": tel.thoughts_tokens,
            "total_tokens": tel.total_tokens,
            "quota_or_rate_limit_errors": tel.quota_or_rate_limit_errors,
            "fallback_events": tel.fallback_events,
        },
    }


def render_evaluation_markdown(report: Dict[str, Any]) -> str:
    """Render structured benchmark report dictionary into concise Markdown tables."""
    lines = [
        "# E3.1 Evaluation Harness Output",
        "",
        f"- **Timestamp (UTC)**: `{report['generated_at']}`",
        f"- **Provider Mode**: `{report['provider']}`",
        f"- **Split Requested**: `{report['split']}`",
        f"- **Embedding Model**: `{report['embedding_model']}`",
        f"- **Reasoning Model**: `{report['reasoning_model']}`",
        "",
    ]
    if report.get("probe") is not None:
        lines.extend(
            [
                "## Model Probe Result",
                f"- Embedding model available: `{report['probe']['embedding_model'].get('available')}`",
                f"- Reasoning model available: `{report['probe']['reasoning_model'].get('available')}`",
                "",
            ]
        )

    for ds_name, ds_res in (report.get("clause_benchmarks") or {}).items():
        lines.extend([f"## Benchmark: `{ds_name}`", ""])
        for split_label, mode_map in ds_res.items():
            lines.append(f"### Split: `{split_label}`")
            lines.append("")
            lines.append(
                "| Config | Recall@1 | Recall@5 | Multi-Ob (Ret/Dec) | Rel Accuracy | Macro F1 | False Eq | False Cov | Unresolved | Citations | Calls (Emb/LLM) | Tokens (Tot/Thgt) | Latency (ms) |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for mode_name, m in mode_map.items():
                t = m["telemetry"]
                tot_tok = t["total_tokens"] or (
                    t["prompt_tokens"] + t["completion_tokens"] + t["thoughts_tokens"]
                )
                multi_str = (
                    f"{m['multi_ob_retrieval_hits']}/{m['multi_ob_decision_hits']}/{m['multi_ob_total']}"
                    if m.get("multi_ob_total")
                    else "N/A"
                )
                lines.append(
                    f"| {mode_name} | {format_metric_ci(m['recall_at_1'], m['retrieval_queries'])} "
                    f"| {format_metric_ci(m['recall_at_5'], m['retrieval_queries'])} "
                    f"| {multi_str} "
                    f"| {format_metric_ci(m['exact_accuracy'], m['n_clauses'])} "
                    f"| {m['macro_f1']*100:.2f}% "
                    f"| {m['false_equivalence']}/{m['n_clauses']} "
                    f"| {m['false_coverage']}/{m['n_clauses']} "
                    f"| {m['unresolved_flagged']}/{m['unresolved_total']} "
                    f"| {m['citation_accurate']}/{m['n_clauses']} "
                    f"| {t['embedding_calls']}/{t['reasoning_calls']} "
                    f"| {tot_tok}/{t['thoughts_tokens']} "
                    f"| {m['elapsed_ms']:.1f} |"
                )
            lines.append("")

    if report.get("questionnaire"):
        lines.extend(
            [
                "## Section 7 Questionnaire Matching",
                "",
                "| Mode | Dev R@1 | Dev R@3 | Holdout R@1 | Holdout R@3 | Confirmed Covered | Latency (ms) |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for mode_name, qm in report["questionnaire"].items():
            lines.append(
                f"| {mode_name} | {qm['dev_r1']}/{qm['dev_total']} | {qm['dev_r3']}/{qm['dev_total']} "
                f"| {qm['ho_r1']}/{qm['ho_total']} | {qm['ho_r3']}/{qm['ho_total']} "
                f"| {qm['confirmed_covered']} | {qm['elapsed_ms']:.1f} |"
            )
        lines.append("")
    return "\n".join(lines)


def run_evaluation_suite(
    *,
    datasets: Dict[str, Sequence[Any]],
    questionnaire_cases: Sequence[Any] = (),
    provider: str = "mock",
    split: str = "all",
    gemini_api_key: Optional[str] = None,
    gemini_billing_tier: str = "free",
    embedding_model: str = "gemini-embedding-001",
    reasoning_model: str = "gemini-2.5-flash",
    rpm_min_interval_seconds: float = 0.0,
    probe_models: bool = False,
    doc_bytes_builder: Optional[Callable[[Sequence[str], str, str], bytes]] = None,
    transport: HttpJsonTransport = default_urllib_json_transport,
    get_transport: HttpGetTransport = default_urllib_json_get_transport,
) -> Dict[str, Any]:
    """Execute full A/B/C evaluation across requested datasets and return JSON/Markdown-ready results."""
    modes = (
        SemanticMatchingMode.DISABLED,
        SemanticMatchingMode.EMBEDDING_ONLY,
        SemanticMatchingMode.HYBRID,
    )
    probe_res: Optional[Dict[str, Any]] = None
    if probe_models and provider == "gemini":
        probe_cfg = build_eval_runtime_config(
            mode=SemanticMatchingMode.HYBRID,
            provider="gemini",
            gemini_api_key=gemini_api_key,
            gemini_billing_tier=gemini_billing_tier,
            gemini_embedding_model=embedding_model,
            gemini_reasoning_model=reasoning_model,
        )
        probe_res = probe_gemini_model_availability(probe_cfg, get_transport=get_transport)

    clause_results: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for ds_name, all_cases in datasets.items():
        subsets: List[Tuple[str, List[Any]]] = []
        if split in {"all", "dev"}:
            dev_items = [c for c in all_cases if c.split == "dev"]
            if dev_items:
                subsets.append(("dev", dev_items))
        if split in {"all", "held_out"}:
            ho_items = [c for c in all_cases if c.split == "held_out"]
            if ho_items:
                subsets.append(("held_out", ho_items))
        if split == "all":
            subsets.append(("combined", list(all_cases)))

        clause_results[ds_name] = {}
        for split_label, sub in subsets:
            clause_results[ds_name][split_label] = {}
            for m in modes:
                cfg = build_eval_runtime_config(
                    mode=m,
                    provider=provider,
                    gemini_api_key=gemini_api_key,
                    gemini_billing_tier=gemini_billing_tier,
                    gemini_embedding_model=embedding_model,
                    gemini_reasoning_model=reasoning_model,
                    rpm_min_interval_seconds=rpm_min_interval_seconds,
                    max_calls_per_run=1000,
                )
                try:
                    clause_results[ds_name][split_label][m.value] = evaluate_clause_benchmark(
                        sub,
                        mode=m,
                        provider=provider,
                        config=cfg,
                        transport=transport,
                        doc_bytes_builder=doc_bytes_builder,
                    )
                except ProviderConfigurationError:
                    raise
                except Exception as exc:
                    raise RuntimeError(
                        f"Benchmark {ds_name}/{split_label}/{m.value} failed: {scrub_secrets(str(exc))}"
                    ) from exc

    q_results: Dict[str, Any] = {}
    if questionnaire_cases:
        filtered_q = (
            list(questionnaire_cases)
            if split == "all"
            else [q for q in questionnaire_cases if q.split == split]
        )
        for m in modes:
            cfg = build_eval_runtime_config(
                mode=m,
                provider=provider,
                gemini_api_key=gemini_api_key,
                gemini_billing_tier=gemini_billing_tier,
                gemini_embedding_model=embedding_model,
                gemini_reasoning_model=reasoning_model,
                rpm_min_interval_seconds=rpm_min_interval_seconds,
                max_calls_per_run=1000,
            )
            q_results[m.value] = evaluate_questionnaire_benchmark(
                filtered_q,
                mode=m,
                provider=provider,
                config=cfg,
                transport=transport,
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "split": split,
        "embedding_model": embedding_model if provider == "gemini" else "mock-concept-v1",
        "reasoning_model": reasoning_model if provider == "gemini" else "mock-deterministic-v1",
        "probe": probe_res,
        "clause_benchmarks": clause_results,
        "questionnaire": q_results,
    }
