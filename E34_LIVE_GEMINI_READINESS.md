# E3.4 Live Google Gemini Evaluation Readiness & Operational Runbook

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Live Gemini Status:** **`LIVE GEMINI: NOT RUN — CREDENTIALS UNAVAILABLE`**  
**Reused Harness:** [`scripts/evaluate_e3_live_gemini.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/evaluate_e3_live_gemini.py) (updated only to accept `--benchmark e34` alongside `e11`, `e3`, `e31`, `e32`, `questionnaire`, `all`)

---

## 1. Credential & Environment Check (Observed 2026-11-20)

| Check | Observed Value | Enforcement Behaviour |
|---|---|---|
| `GEMINI_API_KEY` environment variable | `False` (unset) | CLI fail-closed exit code `2` (`"ERROR: Missing live Gemini credentials..."`) |
| `GOOGLE_API_KEY` environment variable | `False` (unset) | Same fail-closed check in `scripts/evaluate_e3_live_gemini.py` |
| `.env` / `backend/.env` / `web/.env.local` | Absent (only `.env.example` exists) | Zero hardcoded or checked-in secrets (`python scripts/check_secrets.py` passes) |
| Production default (`LLMRuntimeConfig.from_env()`) | `semantic_matching_enabled=False`, `matching_mode=disabled` | Operates strictly in `deterministic_only` mode unless explicitly enabled |

Per Phase 6 assurance requirements, **`LIVE GEMINI: NOT RUN — CREDENTIALS UNAVAILABLE`**. Mock-provider performance (`mock-concept-v1`, `mock-deterministic-v1`) MUST NOT be treated as a predictor of real Google Gemini accuracy.

---

## 2. Supported Models & Lifecycle Audit (`backend/banking_crosswalk/llm/types.py`)

Verified against `GEMINI_MODEL_DEPRECATION_REGISTRY` (`types.py:44–61`) and `LLMRuntimeConfig` (`types.py:120–123`) as of **2026-11-20**:

| Capability | Default Model Configured | Registry Lifecycle Status | Cutoff / Migration Date | Action Required for Operator |
|---|---|---|---|---|
| **Embedding Model** | `gemini-embedding-001` (`256`–`3072` dim, default `256`) | **`active`** | Supported beyond Dec 2026 | Ready for live smoke & evaluation (`:embedContent` & `:batchEmbedContents`) |
| **Reasoning Model** | `gemini-2.5-flash` | **`deprecated_scheduled_migration`** | **`2026-12-01`** (11 days from 2026-11-20) | Automatically emits `ProviderLifecycleWarning`; operator SHOULD override via `--model gemini-3.5-flash-lite` or `GEMINI_REASONING_MODEL=gemini-3.5-flash-lite` once validated on the operator's Gemini project |

---

## 3. Provider Security, Rate Limits, Confidentiality & Fallback Controls

All controls were audited in [`backend/banking_crosswalk/llm/providers.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/providers.py) and [`backend/banking_crosswalk/llm/security.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/llm/security.py) and verified via simulated transport tests (`test_e32_live_gemini_validation.py`):

1. **Credential Isolation (`resolve_provider_api_key`):**
   - `DeploymentEdition.OFFICIAL_HOSTED`: uses server-side `HOSTED_GEMINI_API_KEY` only.
   - `DeploymentEdition.SELF_HOSTED`: strictly rejects/ignores `HOSTED_GEMINI_API_KEY` and requires the tenant/operator's own `GEMINI_API_KEY`.
   - API keys are transmitted strictly via HTTP header `"x-goog-api-key"`, never in URL query strings, and all exceptions/logs pass through `scrub_secrets()`.
2. **Free-Tier Confidentiality Hard Block (`enforce_free_tier_confidentiality`):**
   - `DataClassification.CONFIDENTIAL_ENTERPRISE` is **unconditionally blocked** (HTTP `403` / `ConfidentialityPolicyError` prior to any network call) whenever `GEMINI_BILLING_TIER=free` (even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=true` is set in env).
   - Live free-tier Gemini calls are permitted **only** for `DataClassification.PUBLIC_OR_SYNTHETIC` synthetic benchmark suites or `public-demo`.
   - Note: Live FastAPI `/reconcile` requests (`api.py:1830`) always classify enterprise baselines as `DataClassification.CONFIDENTIAL_ENTERPRISE`, guaranteeing real customer documents cannot reach free-tier Gemini.
3. **Token, Thinking-Budget & Rate Controls:**
   - Gemini `2.5` models share `maxOutputTokens` with thinking tokens; `_generate_structured()` enforces a minimum floor `max(max_output_tokens, 2048)` on `2.5` models, extracts `thoughtsTokenCount` separately, ignores `part.thought == True` parts during JSON extraction, and raises `ProviderOutputError` clearly on `MAX_TOKENS` truncation.
   - `GoogleGeminiProvider._pace_rpm()` enforces configurable sequential spacing (`--rpm-delay`, e.g., `4.2s` for free-tier `15 RPM` limits), layered inside `APICallBudgetTracker` (`max_calls_per_run`, `max_calls_per_minute`, `max_concurrency`).
   - Prompt injection directives inside `<UNTRUSTED_POLICY_CLAUSE>` are neutralized by `sanitize_untrusted_text()`, and outputs must pass strict JSON schema (`_gemini_reconciliation_schema`) + `validate_semantic_citation()`.
4. **Error Handling & Deterministic Fallback:**
   - HTTP `429` (`ProviderQuotaError`), timeouts (`ProviderTimeoutError`), `5xx` (`ProviderUnavailableError`), malformed JSON (`ProviderOutputError`), and ungrounded citations (`CitationVerificationError`) fall back safely to Stage B deterministic reconciliation with telemetry counters (`quota_or_rate_limit_errors`, `citation_rejections`, `fallback_events`), zero auto-approvals (`decision_status != approved`).
5. **Reproducibility Telemetry:**
   - `eval_harness.py` records exact `regulatory_pack_id`, `regulatory_pack_version`, `obligation_count`, `mapping_catalogue_version`, `mapping_count`, `embedding_model`, `reasoning_model`, `lifecycle_warnings`, token breakdown, and per-case classifications.

---

## 4. Exact Reproducible Operator Commands (When Credentials Are Supplied)

**Important Rules:** Never commit API keys (`GEMINI_API_KEY`) to git or `.env` files tracked by git, and never send real confidential customer policies to `GEMINI_BILLING_TIER=free`. Use synthetic datasets (`e34`, `e32`, `e31`) first.

### Step 1 — Model Probe & Small Synthetic Smoke Check (`e32` or `e34`, 100% synthetic data)
```powershell
$env:GEMINI_API_KEY = "<operator-supplied-key>"
$env:PYTHONPATH = "backend;backend/tests"

# 1. Fail-closed probe check + E3.2 synthetic holdout smoke run (~18 clauses, 15s-rated)
#    Override --model gemini-3.5-flash-lite if testing post-Dec-1 target model
.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py `
  --provider gemini `
  --probe-models `
  --benchmark e32 `
  --split held_out `
  --model gemini-3.5-flash-lite `
  --embedding-model gemini-embedding-001 `
  --billing-tier free `
  --rpm-delay 4.2 `
  --output-json live_gemini_e32_smoke.json `
  --output-md live_gemini_e32_smoke.md
```

### Step 2 — Controlled Evaluation on Frozen E3.4 Independent Dataset (`N = 30` clauses + `8` questionnaires)
```powershell
$env:GEMINI_API_KEY = "<operator-supplied-key>"
$env:PYTHONPATH = "backend;backend/tests"

.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py `
  --provider gemini `
  --probe-models `
  --benchmark e34 `
  --split all `
  --model gemini-3.5-flash-lite `
  --embedding-model gemini-embedding-001 `
  --billing-tier free `
  --rpm-delay 4.2 `
  --output-json live_gemini_e34_independent.json `
  --output-md live_gemini_e34_independent.md
```

### Step 3 — Full Synthetic Benchmark Sweep (`e11`, `e3`, `e31`, `e32` — `138` clauses + `22` questionnaires)
```powershell
# Recommended with --billing-tier paid to avoid 15 RPM throttling (~300+ reasoning calls on free tier)
.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py `
  --provider gemini `
  --probe-models `
  --benchmark all `
  --split all `
  --model gemini-3.5-flash-lite `
  --embedding-model gemini-embedding-001 `
  --billing-tier paid `
  --output-json live_gemini_full_results.json `
  --output-md live_gemini_full_report.md
```
