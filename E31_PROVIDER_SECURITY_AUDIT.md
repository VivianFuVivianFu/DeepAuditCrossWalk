# E3.1 Provider Security, Confidentiality & Governance Audit

---

## 1. Security Findings Identified & Remediated in E3.1

### 1.1 `GET /v1/enterprise/llm-status` Free-Tier Confidentiality Misreporting (Fixed)
- **Issue**: In PR #33, [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) computed `"free_tier_confidential_blocked": cfg.gemini_billing_tier == "free" and not cfg.allow_confidential_on_free_tier`, which contradicted [`enforce_free_tier_confidentiality()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/security.py) (which unconditionally rejects `CONFIDENTIAL_ENTERPRISE` workloads when `GEMINI_BILLING_TIER=free`, even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=true`).
- **Fix**: Updated `/v1/enterprise/llm-status` so `"free_tier_confidential_blocked"` is unconditionally `cfg.gemini_billing_tier == "free"`, and added `"effective_confidential_gemini_allowed": cfg.gemini_billing_tier == "paid"`. Verified by `test_e31_llm_status_blocks_confidential_even_with_override`.

### 1.2 Header-Only Secret Handling & Error Scrubbing in Model Probe (Verified)
- Added `probe_gemini_model_availability()` in [`providers.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/providers.py) using `HttpGetTransport` with `x-goog-api-key` headers only (never query string `?key=`), routing non-200 error bodies through `scrub_secrets()`. Verified by `test_e31_gemini_probe_availability_and_key_redaction`.

### 1.3 Citation Grounding & Abbreviated Statutory Reference Hardening (Fixed)
- **Issue**: Strict substring provision checks rejected legitimate statutory shorthand (`"APP 1.1-1.6"`, `"ss 26WE-26WL"`), which would trigger false fallback events under live Gemini inference.
- **Fix**: Updated [`validate_semantic_citation()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/security.py) to normalise punctuation/ranges while still rejecting fabricated provisions (`Section 999`), wrong `cited_obligation_id`, or ungrounded clause quotes (`CitationVerificationError`). Verified by `test_e31_abbreviated_citation_verification_and_rejection`.

### 1.4 Ollama Reference Removal
- Removed leftover `Ollama` documentation references from [`E3_LLM_PROVIDER_INTERFACE.md`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/E3_LLM_PROVIDER_INTERFACE.md) and [`E3_SECURITY_AND_OPEN_SOURCE_CONFIGURATION.md`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/E3_SECURITY_AND_OPEN_SOURCE_CONFIGURATION.md). Tracked repo search confirms zero remaining occurrences.

---

## 2. Core Controls Retained & Verified

| Security Control | Enforcement Mechanism | Verification |
|---|---|---|
| Open-source credential isolation | `CROSSWALK_EDITION=self_hosted` rejects inheriting `HOSTED_GEMINI_API_KEY` (`resolve_provider_api_key`) | `test_e3_05_open_source_edition_and_budget_caps` |
| Free-tier confidentiality block | `enforce_free_tier_confidentiality()` raises `ConfidentialityPolicyError` (`HTTP 403`) on `CONFIDENTIAL_ENTERPRISE` + `free` tier | `test_e3_02`, `test_e31_llm_status_*` |
| Synthetic-only eval permission | `eval_harness.py` / `evaluate_e3_live_gemini.py` force `DataClassification.PUBLIC_OR_SYNTHETIC` strictly for synthetic test suites | CLI & harness unit test |
| SSRF / insecure transport guard | `validate_endpoint_url()` blocks non-HTTPS remote URLs, private-IP bypass patterns, and embedded URL credentials | `test_e3_03` |
| Prompt-injection sanitization | `sanitize_untrusted_text()` strips untrusted directives & truncates to `LLM_MAX_INPUT_CHARS` | `test_e3_04` |
| Quota & budget circuit-breaker | `APICallBudgetTracker` (`max_calls_per_run <= 2000`, `max_calls_per_minute <= 600`), retry on `429`/`5xx`, RPM pacing | `test_e3_04`, `test_e3_05` |
| Truncation / safety fail-closed | `_generate_structured()` rejects `finishReason=MAX_TOKENS` truncated JSON & blocked finish reasons (`SAFETY`, etc.) | `test_e31_gemini_thinking_tokens_and_max_tokens_finish_reason` |
| Stage C deterministic veto | Semantic outputs can never auto-approve coverage (`decision_status` remains `proposed`/`needs_review`, `0%` confirmed coverage) | All E3 & E3.1 benchmarks (`0` false coverage) |
| Tenant & RBAC isolation | `/reconcile` requires `CONTRIBUTOR_ROLES`, rejects `public-demo`, PostgreSQL 16 forced RLS on stored decisions | `test_postgresql_rls_*`, `test_e3_06` |
| Secret scanner gate | `python scripts/check_secrets.py` scans all tracked files | Executed clean (`0` findings) |
