# E3 Gemini Provider & Evaluation Results

> **Transparency Statement**: This environment has **no** `GEMINI_API_KEY` or `GOOGLE_API_KEY` configured. Accordingly, the opt-in live Gemini verification test (`test_e3_07_opt_in_live_gemini_smoke`) **skipped cleanly** during full suite execution. HTTP transport correctness, error handling, header authentication, and deprecation lifecycle tracking for `GoogleGeminiProvider` were verified via mocked HTTP transports, while quantitative retrieval/classification benchmarks below were executed using `DeterministicMockSemanticProvider` (zero-network). Live paid-tier Gemini calibration on real customer documents remains a prerequisite before promoting semantic matching from opt-in to default.

---

## 1. Gemini Model Verification & Deprecation Findings

1. **Embedding Model (`gemini-embedding-001`)**:
   - Configured as default `GEMINI_EMBEDDING_MODEL=gemini-embedding-001` with `GEMINI_EMBEDDING_DIMENSIONS=256` (`outputDimensionality`).
   - Endpoint layout targets the REST `:embedContent` / `:batchEmbedContents` path with `x-goog-api-key` request headers rather than URL query parameters.
2. **Reasoning Model (`gemini-2.5-flash`) & Published Deprecation**:
   - `GEMINI_REASONING_MODEL` defaults to `gemini-2.5-flash` to match initial evaluation scope, paired with an explicit deprecation registry entry in `GEMINI_MODEL_DEPRECATION_REGISTRY`:
     - **Model**: `gemini-2.5-flash`
     - **Cutoff / Auto-reroute Date**: December 1, 2026 (`2026-12-01`)
     - **Published Replacement**: `gemini-3.5-flash-lite`
   - `check_gemini_model_lifecycle()` emits a `ProviderLifecycleWarning` surfaced via `GET /v1/enterprise/llm-status` (`lifecycle_warnings`) and logged into `semantic_provider_meta` on reconciliation decisions.
   - Because `GEMINI_REASONING_MODEL` is runtime-configurable, operators can migrate to `gemini-3.5-flash-lite` (or an OpenAI-compatible private model) via environment configuration with zero code changes.

---

## 2. Gemini Free-Tier Confidentiality Verification

Per Google Gemini API Terms for unpaid ("free tier") usage, prompt and uploaded content may be reviewed or used to improve models. Sending unredacted banking enterprise policies to the free tier therefore creates a data-governance violation.

Implemented and verified enforcement (`backend/banking_crosswalk/llm/security.py` + `tests/test_e3_semantic_matching.py`):

- When `GEMINI_BILLING_TIER=free` (default):
  - `CONFIDENTIAL_ENTERPRISE` data is **unconditionally blocked** with `ConfidentialityPolicyError` (`HTTP 403` at API boundary) — **even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=true` is set in environment config**.
  - Free-tier calls are permitted only for `DataClassification.PUBLIC_OR_SYNTHETIC` / `public-demo` inputs.
- Verified in unit and API tests (`test_e3_03_confidentiality_and_security_controls`, `test_e3_06_api_endpoints_security_rbac_and_matching_mode`), plus fail-closed propagation tests confirming `semantic_reconciliation.py` does **not** catch `ConfidentialityPolicyError` into `deterministic_fallback`.

---

## 3. Protocol, Fault-Tolerance & Citation Grounding Verification

Verified via `test_e3_02_gemini_and_openai_http_protocol_and_deprecation` and `test_e3_04_mock_fault_injection_and_stage_c_veto`:

1. **Auth Header Isolation**: Verified mock HTTP transport receives `x-goog-api-key` in request headers and never in URLs; error messages and telemetry pass through `scrub_secrets()`.
2. **Retry & Backoff on Transient Errors**: Simulated HTTP `429` and timeouts confirm retries obey `LLM_MAX_RETRIES`, returning either succeeded retry responses or cleanly triggering `deterministic_fallback` when retries exhaust.
3. **Structured Schema Rejection**: Injecting malformed JSON or unexpected extra fields (`extra="forbid"` on `SemanticRelationshipAnalysis`) rejects the LLM payload before Stage C without corrupting deterministic classifications.
4. **Fabricated Citation Rejection**: Fault injection `fabricate_citation` fails `validate_semantic_citation()` (`CitationVerificationError` → `ProviderOutputError`) and prevents ungrounded quotes from entering `supporting_passages`.
5. **Overconfident Equivalence Veto**: Fault injection `unsafe_overconfident_equivalent` is intercepted by Stage C `validate_hybrid_candidate_relationship()`, which refuses `EQUIVALENT` when deterministic facets do not prove full equivalence (`0` False Equivalence across all tests).

---

## 4. Opt-In Live Smoke Test Status

| Check | Status in This Verification Run | Condition to Execute |
|---|---|---|
| `test_e3_02_gemini_and_openai_http_protocol_and_deprecation` (mocked HTTP transport) | **PASSED** | Always runs in CI |
| `test_e3_03_confidentiality_and_security_controls` (free-tier block, secret scrub, SSRF check, prompt sanitization) | **PASSED** | Always runs in CI |
| `test_e3_04_mock_fault_injection_and_stage_c_veto` (429/timeout/malformed JSON/fabricated citation/overconfident veto) | **PASSED** | Always runs in CI |
| `test_e3_07_opt_in_live_gemini_smoke` (real `GoogleGeminiProvider` call on synthetic data only) | **SKIPPED** | Set `RUN_GEMINI_LIVE_TESTS=1` and `GEMINI_API_KEY` |

---

## 5. Pre-Production Live Calibration Recommendations

Before turning on Gemini in any staging or production deployment:
1. Run `test_e3_07_opt_in_live_gemini_smoke` with a paid-tier project key (`GEMINI_BILLING_TIER=paid`) to verify network reachability, latency, and quota headroom.
2. Execute `test_e3_08`, `test_e3_09`, and `test_e3_10` or an equivalent evaluation harness against a live paid Gemini key on the Dev split first, verifying token cost per policy, retry rate, citation rejection rate, and Stage C veto rate.
3. Plan model migration from `gemini-2.5-flash` to `gemini-3.5-flash-lite` ahead of December 1, 2026 via `GEMINI_REASONING_MODEL`.
