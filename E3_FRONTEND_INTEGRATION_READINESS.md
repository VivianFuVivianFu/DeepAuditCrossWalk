# E3 Frontend Integration Readiness

> Backend contracts and BFF boundary audit for integrating optional E3 semantic matching controls into the Next.js workspace (`web/`) without weakening existing PR #27–#30 security guarantees or PR #24–#32 coverage-confirmation safeguards.

---

## 1. Existing Backend Surface Ready for Frontend Consumption

No backend API redesign is needed. The FastAPI service (`backend/banking_crosswalk/api.py`) already exposes:

1. **`GET /v1/enterprise/llm-status`** (`READER_ROLES`, rejects `public-demo`):
   - Returns non-sensitive status payload:
     - `edition` (`"self_hosted"` | `"official_hosted"`)
     - `semantic_matching_enabled` (`boolean`)
     - `matching_mode` (`"disabled"` | `"embedding_only"` | `"hybrid"`)
     - `embedding_provider` / `reasoning_provider`
     - `gemini_billing_tier` (`"free"` | `"paid"`)
     - `free_tier_confidential_blocked` (`boolean`)
     - `embedding_model` / `reasoning_model`
     - `lifecycle_warnings` (`ProviderLifecycleWarning[]`, including the `gemini-2.5-flash` Dec 1, 2026 deprecation notice)
   - Contains **no** API keys, endpoint URLs, or tenant secrets.
2. **`POST /v1/enterprise/baselines/{baseline_id}/reconcile`** (`CONTRIBUTOR_ROLES`, rejects `public-demo`):
   - Accepts optional `matching_mode`: `"deterministic_only" | "embedding_only" | "hybrid"`.
   - Returns standard `201` `List[ReconciliationDecision]` with additive E3 provenance fields:
     - `matching_mode` (`"deterministic_only"` | `"embedding_plus_deterministic"` | `"hybrid_embedding_llm_deterministic"` | `"deterministic_fallback"`)
     - `embedding_similarity` (`number | null`)
     - `semantic_analysis` (`object | null`)
     - `semantic_provider_meta` (`object | null`, e.g., lifecycle warnings / fallback diagnostics)
   - Clean error codes for UI handling:
     - `HTTP 403`: Free-tier confidentiality policy block (`CONFIDENTIAL_ENTERPRISE` cannot be sent to Gemini free tier).
     - `HTTP 503`: Semantic mode requested when `SEMANTIC_MATCHING_ENABLED=false` or provider misconfigured.
3. **`GET /v1/enterprise/baselines/{baseline_id}/reconciliations` & `.../unresolved` & `PUT /v1/enterprise/reconciliations/{id}/review`**:
   - Already persist and round-trip the additive E3 metadata fields across SQLite and PostgreSQL 16 (with RLS).

---

## 2. Current State of the Next.js BFF (`web/`)

Auditing [web/app/api/workspace/route.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts):

- The Next.js BFF already supports `reconcile_baseline`, `list_reconciliations`, `list_unresolved_reconciliations`, `review_reconciliation`, `compose_effective_baseline`, and `get_effective_baseline` via CSRF-validated, signed-context (`X-Workspace-Context`) proxying.
- Upstream `4xx` error details (`< 300` chars) are safely surfaced, while `5xx` (except `501`) returns a sanitized `"The backend analysis service is temporarily unavailable."` message.
- **Two small additive wiring items remain for a future UI PR** (intentionally left out of this backend E3 PR to keep UI untouched):
  1. Add a `get_llm_status` action in `web/app/api/workspace/route.ts` (mapped to `READER_ROLES` / `ACTION_PERMISSIONS` in [web/app/security.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/security.ts)) calling `GET /v1/enterprise/llm-status`.
  2. Forward optional validated `matching_mode` (`"deterministic_only" | "embedding_only" | "hybrid"`) inside `reconcile_baseline` in `web/app/api/workspace/route.ts`.

---

## 3. UI Display & Governance Requirements for Future Frontend Work

When exposing E3 controls in [web/app/page.tsx](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/page.tsx):

1. **Matching Mode Selector**: Default to `deterministic_only`; disable or badge `embedding_only` / `hybrid` whenever `/v1/enterprise/llm-status` reports `semantic_matching_enabled === false` or `free_tier_confidential_blocked === true`.
2. **Lifecycle & Fallback Banners**: Display `lifecycle_warnings` (e.g., `gemini-2.5-flash` Dec 1, 2026 reroute warning) and visibly badge `matching_mode === "deterministic_fallback"` decisions so reviewers know LLM analysis degraded safely to deterministic logic.
3. **Human Review Distinction**: Keep `proposed_relationship` / `validated_relationship` / `semantic_analysis` clearly labeled as **review proposals** (`proposed` or `needs_review`), distinct from `approved_relationship` and `Confirmed Covered` assessment counts.
4. **No Client-Side Secrets**: Never collect, store, or transmit `GEMINI_API_KEY` or `LLM_API_KEY` from browser UI inputs; server configuration remains strictly environment/secret-manager owned.
