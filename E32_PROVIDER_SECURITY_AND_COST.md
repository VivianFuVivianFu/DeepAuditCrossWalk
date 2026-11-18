# E3.2 Provider Security, Confidentiality & Cost Governance Audit

## 1. Runtime Security & Confidentiality Verification (Phase 7)

All controls verified by inspection of [`backend/banking_crosswalk/llm/security.py`](backend/banking_crosswalk/llm/security.py), [`providers.py`](backend/banking_crosswalk/llm/providers.py), [`types.py`](backend/banking_crosswalk/llm/types.py), [`api.py`](backend/banking_crosswalk/api.py), and executed tests in [`test_e32_live_gemini_validation.py`](backend/tests/test_e32_live_gemini_validation.py) and `tests/test_e3_semantic_matching.py`:

| Security / Cost Requirement | Enforcement Mechanism | Observed Status |
|---|---|---|
| **Confidential customer data blocked from Gemini free tier** | `api.py` passes `DataClassification.CONFIDENTIAL_ENTERPRISE` unconditionally on `/v1/enterprise/baselines/{id}/reconcile`; `enforce_free_tier_confidentiality()` raises `ConfidentialityPolicyError` (`HTTP 403`) whenever `gemini_billing_tier == "free"` — **even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=true`**. Verified with `_never_post` transport assert (`called == False`). | **Verified Passing** |
| **Zero secrets in logs, errors, URLs, or reports** | `GoogleGeminiProvider` sends keys only via `x-goog-api-key` HTTP headers (never `?key=` URL query strings); HTTP/network errors and `probe_gemini_model_availability()` route through `scrub_secrets()`; `LLMRuntimeConfig` marks API key fields `exclude=True, repr=False`; `scripts/check_secrets.py` scans all publishable files. | **Verified Passing** |
| **Open-source / self-hosted credential isolation** | `CROSSWALK_EDITION=self_hosted` strictly requires user-supplied `GEMINI_API_KEY` or `LLM_*_API_KEY` and rejects inheriting `HOSTED_GEMINI_API_KEY` (`resolve_provider_api_key`). | **Verified Passing** |
| **Deterministic default without credentials** | `SEMANTIC_MATCHING_ENABLED` defaults to `false` (`SemanticMatchingMode.DISABLED`). With zero LLM credentials, all regulatory, applicability, reconciliation, and coverage APIs operate deterministically. | **Verified Passing** |
| **No public / anonymous Hybrid Matching** | Anonymous `/api/analysis` stays restricted to stateless `DEMO_BANKING_V1` in `public-demo`; `/v1/enterprise/*` rejects `public-demo` and requires authenticated contributor/reviewer RBAC + CSRF + PostgreSQL RLS. | **Verified Passing** |
| **Budgets, rate limits & concurrency caps** | `APICallBudgetTracker` enforces thread-safe `max_calls_per_run` (default `40`, ceiling `2000`), `max_calls_per_minute` (default `30`, ceiling `600`), `max_concurrency` semaphore (default `4`), plus `rpm_min_interval_seconds` pacing (`4.2s` recommended for 15 RPM free tier). | **Verified Passing** |
| **Resilience to 429, timeout, invalid JSON, truncated output & bad model** | Tested live-transport simulation: HTTP `429` increments `quota_or_rate_limit_errors` & `fallback_events` and degrades to deterministic Stage B/C without auto-approval; `finishReason=MAX_TOKENS` & `SAFETY` fail closed; `404` model probe returns `available=False` safely. | **Verified Passing** |
| **Human-approval invariant** | Stage C/D hard-clamps `decision_status` so semantic pipelines **never** emit `APPROVED` (`0` confirmed coverage across all evaluations). | **Verified Passing** |

---

## 2. Live Project Quotas, Latency & Cost Posture

- **Actual Project Limits / Free-Tier Quotas:** **NOT MEASURED (`NOT RUN — CREDENTIALS UNAVAILABLE`)**. Do not assume published Gemini free-tier RPM/TPM limits remain active on any target Google Cloud / AI Studio project without running `--probe-models` and a bounded canary with `--billing-tier free --rpm-delay 4.2`.
- **Configurable Model Strategy:**
  - `GEMINI_EMBEDDING_MODEL` defaults to `gemini-embedding-001` (registry status: `active`).
  - `GEMINI_REASONING_MODEL` defaults to `gemini-2.5-flash` (flagged in `GEMINI_MODEL_DEPRECATION_REGISTRY` with lifecycle warning prior to `2026-12-01` migration toward `gemini-3.5-flash-lite`; `telemetry.lifecycle_warnings` alerts operators when deprecated IDs are used).
- **Offline Mock Call Volume (Upper-Bound Request Footprint Reference):**
  - Running `all` benchmarks (`N=138` clauses + `22` questionnaire items, 3 splits/combined sweeps): Config C issued `183` cached/batched embedding calls (`26` questionnaire + `157` clause runs) and `413` reasoning calls (`344` clause + `69` questionnaire) in mock mode.
  - Because free-tier RPM pacing at `4.2s/req` serializes ~413 reasoning calls to ~29 minutes for a full combined+split sweep, operators running free-tier live evaluation should execute `--split held_out` or individual benchmarks first (e.g. `--benchmark e32 --split held_out`: `23` embedding calls + `44` reasoning calls ≈ ~4.7 minutes at `4.2s` pacing).
- **Monetary API Cost (`estimated_cost_usd`):** **`NOT RUN — CREDENTIALS UNAVAILABLE`** (mock mode reports `null`).
