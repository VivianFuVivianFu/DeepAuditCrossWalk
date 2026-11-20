"""E3.2 Live Gemini Accuracy Validation, Benchmark Integrity & Safety Controls Tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from banking_crosswalk.llm import (
    ConfidentialityPolicyError,
    DataClassification,
    DeploymentEdition,
    LLMProviderKind,
    LLMRuntimeConfig,
    ProviderConfigurationError,
    SemanticMatchingMode,
    build_provider_bundle,
    probe_gemini_model_availability,
)
from banking_crosswalk.llm.eval_harness import (
    evaluate_questionnaire_benchmark,
    render_evaluation_markdown,
    run_evaluation_suite,
)
from banking_crosswalk.models import BankingUseCase, ReconciliationDecisionStatus
from banking_crosswalk.semantic_reconciliation import generate_hybrid_reconciliation_candidates
from e11_benchmark_dataset import _build_docx_bytes, _build_pdf_bytes
from e32_independent_holdout import E32_INDEPENDENT_HOLDOUT, E32_QUESTIONNAIRE_HOLDOUT

ROOT = Path(__file__).resolve().parents[2]


def _doc_bytes(paras, fmt, title):
    if fmt == "pdf":
        return _build_pdf_bytes(paras, title)
    if fmt == "docx":
        return _build_docx_bytes(paras)
    return ("\n\n".join(paras)).encode("utf-8")


def test_e32_harness_loads_pack_020_and_independent_holdout_offline():
    assert len(E32_INDEPENDENT_HOLDOUT) == 18
    assert all(c.split == "held_out" for c in E32_INDEPENDENT_HOLDOUT)
    assert len(E32_QUESTIONNAIRE_HOLDOUT) == 4

    report = run_evaluation_suite(
        datasets={"e32": E32_INDEPENDENT_HOLDOUT},
        questionnaire_cases=E32_QUESTIONNAIRE_HOLDOUT,
        provider="mock",
        split="all",
        doc_bytes_builder=_doc_bytes,
    )
    assert report["regulatory_pack_version"] == "0.2.0"
    assert report["obligation_count"] == 46
    assert report["mapping_catalogue_version"] == "1.1.0"
    assert report["mapping_count"] == 55

    ho = report["clause_benchmarks"]["e32"]["held_out"]
    for cfg in ("disabled", "embedding_only", "hybrid"):
        metrics = ho[cfg]
        assert metrics["n_clauses"] == 18
        assert metrics["false_equivalence"] == 0
        assert metrics["false_coverage"] == 0
        assert metrics["citation_accurate"] == 18
        assert "by_authority_layer" in metrics
        assert "by_risk_category" in metrics
        assert "false_positive_coverage_proposals" in metrics

    md = render_evaluation_markdown(report)
    assert "v`0.2.0`" in md
    assert "`46` obligations" in md
    assert "## Benchmark: `e32`" in md

    q_res = report["questionnaire"]["hybrid"]
    assert q_res["confirmed_covered"] == 0
    assert q_res["all_proposed"] is True


def test_e32_real_gemini_http_pipeline_with_simulated_gemini_25_and_error_fallbacks(monkeypatch):
    """Verify actual GoogleGeminiProvider Config B & C code paths without network."""
    fake_api_key = "AIzaSyE32SimulatedTestKey1234567890"
    seen_headers = []

    def _fake_get(url: str, headers: dict, timeout: float):
        seen_headers.append((url, dict(headers)))
        if url.endswith("/models/gemini-embedding-001"):
            return 200, json.dumps(
                {
                    "name": "models/gemini-embedding-001",
                    "supportedGenerationMethods": ["embedContent", "batchEmbedContents"],
                    "inputTokenLimit": 2048,
                }
            )
        if url.endswith("/models/gemini-2.5-flash"):
            return 200, json.dumps(
                {
                    "name": "models/gemini-2.5-flash",
                    "supportedGenerationMethods": ["generateContent"],
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 65536,
                }
            )
        return 200, json.dumps(
            {
                "models": [
                    {
                        "name": "models/gemini-embedding-001",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            }
        )

    def _fake_post(url: str, headers: dict, payload: dict, timeout: float):
        seen_headers.append((url, dict(headers)))
        if ":batchEmbedContents" in url:
            n = len(payload.get("requests") or [])
            return 200, json.dumps({"embeddings": [{"values": [0.5] * 256} for _ in range(n)]})
        if ":embedContent" in url:
            return 200, json.dumps({"embedding": {"values": [0.5] * 256}})
        if ":generateContent" in url:
            usr_obj = json.loads(payload["contents"][0]["parts"][0]["text"])
            ob = usr_obj["CANDIDATE_REGULATORY_OBLIGATION"]
            if usr_obj.get("task") == "questionnaire_semantic_candidate":
                q_id = usr_obj["question_id"]
                q_txt = usr_obj["UNTRUSTED_QUESTION_TEXT"]
                resp_obj = {
                    "question_id": q_id,
                    "external_obligation_id": ob["obligation_id"],
                    "cited_obligation_id": ob["obligation_id"],
                    "cited_provision": ob["provision"],
                    "semantic_relevance": "high",
                    "confidence": 0.85,
                    "candidate_covered_facets": list(ob["required_facets"])[:1],
                    "missing_facets": [],
                    "uncertainty_flags": ["Proposed candidate only."],
                    "supporting_question_quote": q_txt[:140],
                    "supporting_obligation_quote": f"{ob['provision']}: {ob['summary']}"[:140],
                    "reasoning_summary": "Verified simulated Gemini questionnaire candidate.",
                }
            else:
                clause_id = usr_obj["clause_id"]
                clause_txt = usr_obj["UNTRUSTED_POLICY_CLAUSE"]
                resp_obj = {
                    "clause_id": clause_id,
                    "external_obligation_id": ob["obligation_id"],
                    "cited_obligation_id": ob["obligation_id"],
                    "cited_provision": ob["provision"],
                    "proposed_relationship": "partially_overlapping",
                    "semantic_relevance": "high",
                    "confidence": 0.86,
                    "operational_scope": "enterprise_general",
                    "required_actions_and_prohibitions": ["mandatory_control_action"],
                    "approval_authority": None,
                    "timing": None,
                    "numerical_thresholds": [],
                    "conditions_and_exceptions": [],
                    "potential_contradiction": False,
                    "contradiction_detail": None,
                    "missing_requirement_facets": [],
                    "inferred_covered_facets": list(ob["required_facets"])[:1],
                    "uncertainty_flags": ["Synthetic simulated Gemini verification."],
                    "supporting_clause_quote": clause_txt[:140],
                    "supporting_obligation_quote": f"{ob['provision']}: {ob['summary']}"[:140],
                    "reasoning_summary": "Verified simulated Gemini structured JSON output.",
                }
            return 200, json.dumps(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"thought": True, "text": "internal thought trace"},
                                    {"text": json.dumps(resp_obj)},
                                ]
                            },
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 310,
                        "candidatesTokenCount": 95,
                        "thoughtsTokenCount": 140,
                        "totalTokenCount": 545,
                    },
                }
            )
        return 404, json.dumps({"error": "unknown"})

    subset = E32_INDEPENDENT_HOLDOUT[:2]
    report = run_evaluation_suite(
        datasets={"e32": subset},
        questionnaire_cases=E32_QUESTIONNAIRE_HOLDOUT[:1],
        provider="gemini",
        split="held_out",
        gemini_api_key=fake_api_key,
        gemini_billing_tier="free",
        probe_models=True,
        transport=_fake_post,
        get_transport=_fake_get,
        doc_bytes_builder=_doc_bytes,
    )
    assert report["probe"]["embedding_model"]["available"] is True
    assert report["probe"]["reasoning_model"]["available"] is True
    hyb = report["clause_benchmarks"]["e32"]["held_out"]["hybrid"]
    assert hyb["provider"] == "gemini"
    assert hyb["false_coverage"] == 0
    assert hyb["telemetry"]["thoughts_tokens"] > 0
    assert hyb["telemetry"]["total_tokens"] > hyb["telemetry"]["thoughts_tokens"]
    # API keys sent only via x-goog-api-key header, never in URL query strings
    assert all("key=" not in url.lower() for url, _ in seen_headers)
    assert all(h.get("x-goog-api-key") == fake_api_key for _, h in seen_headers)


def test_e32_runtime_security_confidentiality_fallbacks_and_default_deterministic(monkeypatch):
    # Default config without credentials operates strictly deterministic
    monkeypatch.delenv("SEMANTIC_MATCHING_ENABLED", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("HOSTED_GEMINI_API_KEY", raising=False)
    default_cfg = LLMRuntimeConfig.from_env()
    assert default_cfg.semantic_matching_enabled is False
    assert default_cfg.matching_mode is SemanticMatchingMode.DISABLED

    # Confidential enterprise payload is strictly blocked from Gemini free tier before any HTTP call
    called = False

    def _never_post(url, headers, payload, timeout):
        nonlocal called
        called = True
        return 200, "{}"

    free_cfg = LLMRuntimeConfig(
        edition=DeploymentEdition.SELF_HOSTED,
        semantic_matching_enabled=True,
        matching_mode=SemanticMatchingMode.HYBRID,
        embedding_provider=LLMProviderKind.GEMINI,
        reasoning_provider=LLMProviderKind.GEMINI,
        gemini_api_key="AIzaSyDummyKeyNeverSentToNetwork123",
        gemini_billing_tier="free",
        allow_confidential_on_free_tier=True,  # even override flag cannot permit confidential data on free tier
    )
    bundle = build_provider_bundle(free_cfg, transport=_never_post)
    q_res = evaluate_questionnaire_benchmark(
        E32_QUESTIONNAIRE_HOLDOUT[:1],
        mode=SemanticMatchingMode.EMBEDDING_ONLY,
        provider="mock",
    )
    assert q_res["confirmed_covered"] == 0

    with pytest.raises(ConfidentialityPolicyError):
        bundle.embed_with_cache(
            ["confidential bank policy text"],
            data_classification=DataClassification.CONFIDENTIAL_ENTERPRISE,
            tenant_id="real-bank-tenant",
        )
    assert called is False

    # Simulated 429 on Gemini reasoning degrades safely to deterministic fallback & records telemetry
    def _post_429_rsn(url, headers, payload, timeout):
        if ":batchEmbedContents" in url:
            n = len(payload.get("requests") or [])
            return 200, json.dumps({"embeddings": [{"values": [0.2] * 256} for _ in range(n)]})
        if ":embedContent" in url:
            return 200, json.dumps({"embedding": {"values": [0.2] * 256}})
        return 429, json.dumps({"error": {"message": "Quota exceeded AIzaSySecretShouldBeScrubbed123456"}})

    from banking_crosswalk.catalog import load_regulatory_pack
    from banking_crosswalk.policy import compile_enterprise_baseline, extract_enterprise_policy
    from banking_crosswalk.models import ClauseReviewStatus

    pol = extract_enterprise_policy(
        tenant_id="t-e32-fallback",
        name="Fallback Test Policy",
        text=E32_INDEPENDENT_HOLDOUT[0].raw_text,
        created_by="test",
    )
    pol = pol.model_copy(
        update={
            "clauses": [
                c.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
                for c in pol.clauses
            ]
        }
    )
    baseline = compile_enterprise_baseline(
        tenant_id="t-e32-fallback",
        name="Fallback Baseline",
        policies=[pol],
        created_by="test",
    )
    paid_cfg = free_cfg.model_copy(
        update={"gemini_billing_tier": "paid", "max_retries": 0, "retry_backoff_seconds": 0.0}
    )
    paid_bundle = build_provider_bundle(paid_cfg, transport=_post_429_rsn)
    decs, meta = generate_hybrid_reconciliation_candidates(
        tenant_id="t-e32-fallback",
        enterprise_baseline=baseline,
        policies=[pol],
        regulatory_pack=load_regulatory_pack(),
        use_case=BankingUseCase(handles_personal_information=True),
        config=paid_cfg,
        bundle=paid_bundle,
        data_classification=DataClassification.CONFIDENTIAL_ENTERPRISE,
    )
    assert decs
    assert all(d.decision_status is not ReconciliationDecisionStatus.APPROVED for d in decs)
    assert paid_bundle.telemetry.quota_or_rate_limit_errors >= 1
    assert paid_bundle.telemetry.fallback_events >= 1
    assert "AIzaSySecret" not in json.dumps(meta)

    # Probe handles unsupported/404 model cleanly without throwing secrets
    probe = probe_gemini_model_availability(
        paid_cfg.model_copy(update={"gemini_reasoning_model": "gemini-nonexistent-99"}),
        get_transport=lambda url, h, t: (
            404,
            '{"error": "not found at https://api.example?key=secret123 AIzaSyFakeKeyToScrub123456"}',
        ),
    )
    assert probe["reasoning_model"]["available"] is False
    assert "secret123" not in json.dumps(probe)
    assert "AIzaSyFakeKey" not in json.dumps(probe)


def test_e32_deliverables_exist():
    required = [
        "E32_LIVE_GEMINI_BENCHMARK.md",
        "E32_BENCHMARK_INTEGRITY_AUDIT.md",
        "E32_MATCHING_FAILURE_ANALYSIS.md",
        "E32_PROVIDER_SECURITY_AND_COST.md",
        "E32_RELEASE_READINESS_DECISION.md",
        "E32_BENCHMARK_RESULTS.json",
    ]
    for name in required:
        p = ROOT / name
        assert p.exists(), f"Missing E3.2 deliverable: {name}"
        assert p.stat().st_size > 0, f"Empty E3.2 deliverable: {name}"
