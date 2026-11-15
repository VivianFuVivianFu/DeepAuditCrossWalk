# E3 Provider-Agnostic LLM & Embedding Provider Interface

> Backend-only, transport-injectable abstraction separating embeddings from reasoning and decoupling DeepAudit Crosswalk from any single AI vendor.

---

## 1. Core Protocols (`backend/banking_crosswalk/llm/providers.py`)

DeepAudit Crosswalk defines two independent Python protocols rather than requiring a monolithic SDK:

1. **`EmbeddingProvider`**:
   - Dense vector generation for retrieval (`embed(EmbeddingRequest) -> EmbeddingResult`).
   - Supports configurable embedding model, output dimensionality (e.g., `GEMINI_EMBEDDING_DIMENSIONS=256`), and task type (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` / `SEMANTIC_SIMILARITY`).
2. **`ReasoningProvider`**:
   - Structured semantic analysis (`analyze_reconciliation(...) -> SemanticRelationshipAnalysis`, `analyze_questionnaire_match(...) -> QuestionnaireSemanticMatchAnalysis`).
   - Produces strict Pydantic-validated JSON objects (`extra="forbid"`).

`SemanticProviderBundle` (constructed via `build_provider_bundle(config)`) allows mixing providers independently — for example:
- **Embeddings only** (`SEMANTIC_MATCHING_MODE=embedding_only`) with `LLM_REASONING_PROVIDER=disabled`
- **Google Gemini** for embeddings (`gemini-embedding-001`) + **Self-hosted OpenAI-compatible** vLLM/Ollama/enterprise gateway for reasoning
- **DeterministicMockSemanticProvider** (`LLM_EMBEDDING_PROVIDER=mock`, `LLM_REASONING_PROVIDER=mock`) for offline CI and fault-injection testing

---

## 2. Implemented Providers

### 2.1 `GoogleGeminiProvider`
- **Protocol**: Direct Gemini REST API (`generativelanguage.googleapis.com`) using `x-goog-api-key` header (keys are never placed in URL query strings, keeping proxy/HTTP logs clean).
- **Default Models**:
  - Embedding: `gemini-embedding-001` (supports Matryoshka dimension reduction via `outputDimensionality`, default `256`).
  - Reasoning: Configurable via `GEMINI_REASONING_MODEL` (configured default in `.env.example`: `gemini-2.5-flash`).
- **Deprecation & Lifecycle Governance**:
  - `GEMINI_MODEL_DEPRECATION_REGISTRY` and `check_gemini_model_lifecycle(model)` track `gemini-2.5-flash` deprecation and published December 1, 2026 auto-rerouting to `gemini-3.5-flash-lite`.
  - Warnings surface automatically on `GET /v1/enterprise/llm-status` (`lifecycle_warnings`) and in `semantic_provider_meta` without breaking API compatibility.
- **Reliability**: Exponential backoff / retry handling for HTTP `429`, `5xx`, and request timeouts (`LLM_MAX_RETRIES`, `LLM_REQUEST_TIMEOUT_SECONDS`), plus `APICallBudgetTracker` (`max_calls_per_run <= 500`, `max_calls_per_minute <= 600`).

### 2.2 `OpenAICompatibleProvider`
- **Protocol**: Standard `/embeddings` and `/chat/completions` REST endpoints over HTTPS (validated via `validate_endpoint_url()`, preventing SSRF to unencrypted HTTP remote hosts).
- **Split Capability Support**:
  - Supports shared (`LLM_BASE_URL`, `LLM_API_KEY`) or separate (`LLM_EMBEDDING_BASE_URL` / `LLM_EMBEDDING_API_KEY`, `LLM_REASONING_BASE_URL` / `LLM_REASONING_API_KEY`) configurations.
  - Graceful degradation flags:
    - `LLM_EMBEDDING_SUPPORTED=false` omits embedding calls cleanly.
    - `LLM_STRUCTURED_OUTPUT_SUPPORTED=false` omits `response_format` (`json_schema` / `json_object`) for local/legacy gateways and parses/validates extracted JSON against Pydantic schemas.

### 2.3 `DeterministicMockSemanticProvider`
- **Purpose**: Zero-network, reproducible evaluation and fault-injection provider for CI and regression tests.
- **Fault Injection Modes**: `simulate_429`, `simulate_timeout`, `malformed_json`, `fabricate_citation`, `unsafe_overconfident_equivalent`.
- Used to prove that Stage B schema checks, `validate_semantic_citation()`, retry/timeout handling, and Stage C deterministic vetoes behave identically regardless of upstream model claims.

---

## 3. Typed Error Hierarchy (`backend/banking_crosswalk/llm/types.py`)

| Exception | Cause | Runtime Behaviour |
|---|---|---|
| `ConfidentialityPolicyError` | Confidential policy sent under `GEMINI_BILLING_TIER=free` | **Fail-closed** (`HTTP 403`) — never falls back |
| `ProviderConfigurationError` | Missing credentials / invalid endpoint URL / insecure scheme | **Fail-closed** (`HTTP 503`) — never falls back |
| `ProviderQuotaError` | Upstream HTTP `429` or `APICallBudgetTracker` exhaustion | Retries up to `LLM_MAX_RETRIES`, then `deterministic_fallback` |
| `ProviderTimeoutError` | Socket / request timeout exceeding `LLM_REQUEST_TIMEOUT_SECONDS` | Retries, then `deterministic_fallback` |
| `ProviderUnavailableError` | Upstream `5xx` or network unreachability | Retries, then `deterministic_fallback` |
| `CitationVerificationError` | Quoted `supporting_quote` absent from source policy clause | Treated as `ProviderOutputError` → rejected / fallback |
| `ProviderOutputError` | Malformed JSON, extra/forbidden keys, invalid schema, bad citation | Rejected; falls back to deterministic result |

All error messages surfaced via HTTP responses or stored telemetry pass through `scrub_secrets()` so API keys or bearer tokens cannot leak.

---

## 4. API Endpoints (`backend/banking_crosswalk/api.py`)

- `POST /v1/enterprise/baselines/{baseline_id}/reconcile` (also `/enterprise-baselines/{baseline_id}/reconcile`):
  - Optional `matching_mode` override in request body: `"deterministic_only" | "embedding_only" | "hybrid"`.
  - If `embedding_only` or `hybrid` is requested when `SEMANTIC_MATCHING_ENABLED=false`, returns `HTTP 503`.
  - If server policy blocks free-tier confidential processing, returns `HTTP 403`.
  - Requires `CONTRIBUTOR_ROLES` and rejects `public-demo` tenant.
- `GET /v1/enterprise/llm-status`:
  - Requires `READER_ROLES`, rejects `public-demo` tenant.
  - Returns non-secret runtime metadata (`edition`, `semantic_matching_enabled`, `matching_mode`, `embedding_provider`, `reasoning_provider`, `gemini_billing_tier`, `free_tier_confidential_blocked`, `embedding_model`, `reasoning_model`, `lifecycle_warnings`) with zero API keys or endpoints exposed.
