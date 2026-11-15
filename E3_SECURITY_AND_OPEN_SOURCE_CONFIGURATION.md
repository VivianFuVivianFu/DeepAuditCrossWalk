# E3 Security & Open-Source Configuration Guide

> How Apache-2.0 self-hosted deployments and official hosted deployments isolate credentials, prevent confidential data leaks to free-tier LLM APIs, and control spend/SSRF/prompt-injection risk.

---

## 1. Edition Isolation (`CROSSWALK_EDITION`)

| Variable | Allowed Values | Default | Behaviour |
|---|---|---|---|
| `CROSSWALK_EDITION` | `self_hosted`, `official_hosted` | `self_hosted` | In `self_hosted`, provider resolution (`resolve_provider_api_key()`) requires user-supplied credentials (`GEMINI_API_KEY`, `LLM_API_KEY`, etc.) and **never reads or inherits `HOSTED_GEMINI_API_KEY`**. Only `official_hosted` reads `HOSTED_GEMINI_API_KEY`. |
| `SEMANTIC_MATCHING_ENABLED` | `true`, `false` | `false` | Master kill-switch. When `false`, zero outbound embedding or LLM calls occur and `POST /reconcile` with `matching_mode=embedding_only\|hybrid` returns `HTTP 503`. |
| `SEMANTIC_MATCHING_MODE` | `disabled`, `embedding_only`, `hybrid` | `disabled` | Controls default Stage A / Stage B execution when enabled. |
| `LLM_EMBEDDING_PROVIDER` | `disabled`, `mock`, `gemini`, `openai_compatible` | `disabled` | Selects embedding backend independently of reasoning backend. |
| `LLM_REASONING_PROVIDER` | `disabled`, `mock`, `gemini`, `openai_compatible` | `disabled` | Selects structured reasoning backend independently of embedding backend. |

Verified by `test_e3_05_open_source_edition_and_budget_caps`: setting `HOSTED_GEMINI_API_KEY` under `CROSSWALK_EDITION=self_hosted` raises `ProviderConfigurationError` rather than silently using the hosted key.

---

## 2. Hard Confidentiality Boundary for Free-Tier Gemini

- `GEMINI_BILLING_TIER` (`free` | `paid`, default `free`)
- `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER` (default `false`)

**Hard Fail-Closed Guarantee**: In `enforce_free_tier_confidentiality()` (`backend/banking_crosswalk/llm/security.py`), enterprise policy documents carry `DataClassification.CONFIDENTIAL_ENTERPRISE` by default on `POST /v1/enterprise/baselines/{baseline_id}/reconcile`. Whenever `GEMINI_BILLING_TIER=free`, calling Gemini on `CONFIDENTIAL_ENTERPRISE` data raises `ConfidentialityPolicyError` (`HTTP 403`) — **even if `ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=true` is configured**. Free-tier Gemini is allowed exclusively for `PUBLIC_OR_SYNTHETIC` / `public-demo` workloads.

---

## 3. Environment Variables Reference (from [`.env.example`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/.env.example))

### Core & Gemini Settings
```env
CROSSWALK_EDITION=self_hosted
SEMANTIC_MATCHING_ENABLED=false
SEMANTIC_MATCHING_MODE=disabled
LLM_EMBEDDING_PROVIDER=disabled
LLM_REASONING_PROVIDER=disabled

GEMINI_API_KEY=
HOSTED_GEMINI_API_KEY=
GEMINI_BILLING_TIER=free
ALLOW_CONFIDENTIAL_LLM_ON_FREE_TIER=false
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_REASONING_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_DIMENSIONS=256
```

### Generic OpenAI-Compatible Settings (Private VPC / Ollama / vLLM / Gateway)
```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_EMBEDDING_BASE_URL=
LLM_EMBEDDING_API_KEY=
LLM_EMBEDDING_MODEL=
LLM_EMBEDDING_SUPPORTED=true
LLM_REASONING_BASE_URL=
LLM_REASONING_API_KEY=
LLM_REASONING_MODEL=
LLM_STRUCTURED_OUTPUT_SUPPORTED=true
```

### Timeouts, Concurrency & Hard Budget Caps
```env
LLM_REQUEST_TIMEOUT_SECONDS=15.0
LLM_MAX_RETRIES=2
LLM_MAX_CONCURRENCY=4
LLM_MAX_CALLS_PER_RUN=40
LLM_MAX_CALLS_PER_MINUTE=30
LLM_MAX_INPUT_CHARS=4000
LLM_MAX_OUTPUT_TOKENS=1024
```

Runtime validation caps `LLM_MAX_CALLS_PER_RUN <= 500` and `LLM_MAX_CALLS_PER_MINUTE <= 600` (`LLMRuntimeConfig.from_env()`), rejecting out-of-range values fail-closed.

---

## 4. Application Security Controls (`backend/banking_crosswalk/llm/security.py`)

1. **Endpoint SSRF & Transport Protection (`validate_endpoint_url`)**: Rejects non-HTTPS remote URLs (HTTP permitted strictly for explicit local loopback development such as `http://localhost` / `http://127.0.0.1` only if allowed, blocking plain HTTP external hosts, embedded URL credentials, and unsafe schemes).
2. **Prompt-Injection Defense (`sanitize_untrusted_text`)**: Neutralizes embedded system-role hijacks (`ignore previous instructions`, `<|im_start|>`, etc.) in uploaded policy clauses before constructing prompts, replacing directives with `"[sanitized-untrusted-directive]"`, plus length truncation at `LLM_MAX_INPUT_CHARS`.
3. **Header-Based Secret Transmission & Redaction (`scrub_secrets`)**: Gemini keys are sent solely via `x-goog-api-key` headers (never URL query params). Exceptions, logs, and API error details are scrubbed so secrets never leak to HTTP clients or audit tables.
4. **RBAC & Tenant Isolation**:
   - Both `/reconcile` (`CONTRIBUTOR_ROLES`) and `GET /v1/enterprise/llm-status` (`READER_ROLES`) reject `public-demo` tenant headers and enforce PostgreSQL 16 RLS tenant isolation on stored `ReconciliationDecision` metadata (`embedding_similarity`, `semantic_analysis`, `semantic_provider_meta`, `matching_mode`).
5. **Secret Scanning Gate**: `python scripts/check_secrets.py` verifies no credential patterns appear in tracked code or documentation.
