# E3.1 Customer-Facing Frontend Integration Readiness Decision

## Release Gate Decision: **`NO-GO` for Customer-Facing Frontend Integration in This Release**

*(Backend semantic matching remains **opt-in / dark-launched** via `SEMANTIC_MATCHING_ENABLED=false` default for operator/synthetic testing only. Keep customer-facing frontend controls disabled until both live Gemini empirical validation and the gateway/UI contract items below are completed in a dedicated follow-up PR.)*

---

## 1. Blocking Evidence Supporting `NO-GO`

### 1.1 Live Gemini Calibration Is Still Unmeasured (`NOT RUN — CREDENTIALS UNAVAILABLE`)
- All quantitative measurements on this branch reflect **Deterministic (`disabled`)** and **`DeterministicMockSemanticProvider`** baselines (`E3 Extended Holdout=19/30 [63.33%]`, `E3.1 Adversarial Holdout=7/12 [58.33%]`), not live `gemini-embedding-001` + `gemini-2.5-flash` inference.
- Real-world held-out accuracy, false-conflict rate, JSON schema compliance, thinking-token latency/cost, and HTTP `429` fallback rates under live Gemini must be empirically validated via `scripts/evaluate_e3_live_gemini.py --provider gemini` before exposing hybrid controls to external users.

### 1.2 Verified Next.js Frontend & BFF Gateway Gaps (Observed in Current Branch)
Direct source inspection of [`web/app/security.ts`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/security.ts), [`web/app/api/workspace/route.ts`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts), and [`web/app/page.tsx`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/page.tsx) confirmed the following unimplemented frontend contracts:

| Component | Current State Verified in Codebase | Missing Requirement for Frontend Release |
|---|---|---|
| `web/app/security.ts` (`ACTION_PERMISSIONS`) | Maps `reconcile_baseline`, `list_reconciliations`, `list_unresolved_reconciliations`, `review_reconciliation` | Missing `"get_llm_status": "baseline:read"` (or dedicated status permission) |
| `web/app/api/workspace/route.ts` (`reconcile_baseline`, L591–L611) | Forwards only `use_case`, `include_non_applicable`, `force_regenerate` | Does **not** validate/forward `matching_mode` (`"deterministic_only" \| "embedding_only" \| "hybrid"`), nor proxy `GET /v1/enterprise/llm-status` |
| `web/app/page.tsx` | `Select-String` shows **zero** UI elements referencing `reconcile*`, `semantic`, `matching_mode`, or `llm-status` | No workspace reconciliation panel, citation evidence viewer, fallback banner, or confidentiality warning UX |

---

## 2. Mandatory Contract Requirements Before Future Frontend `GO`

When a follow-up Frontend Integration PR is scheduled **after** live Gemini calibration passes on locked held-out benchmarks:

1. **BFF Gateway Contract (`web/app/security.ts` + `web/app/api/workspace/route.ts`)**:
   - Add `get_llm_status` action proxying `GET /v1/enterprise/llm-status` with RBAC enforcement.
   - Allow `reconcile_baseline` to forward strictly validated `matching_mode` values (`"deterministic_only" | "embedding_only" | "hybrid"`), never forwarding client API keys or tier overrides.
   - Surface clean HTTP `403` (`free_tier_confidential_blocked`) and `503` (`semantic_matching_enabled=false` / missing key) messages without internal tracebacks.
2. **Mandatory UI Safety & Provenance Surfaces (`web/app/page.tsx`)**:
   - **`proposed` / `needs_review` vs `approved` Separation**: Semantic matches must visually render as *Proposed / Needs Human Review* until a reviewer explicitly records `review_reconciliation` sign-off; must never count toward Confirmed Coverage meters beforehand.
   - **Grounded Citation & Evidence Drawer**: Display `external_obligation_id`, `external_provision`, `supporting_clause_quote`, `supporting_obligation_quote`, `matching_mode`, and `uncertainties`.
   - **Resilience & Deprecation Banners**:
     - Show an explicit *"Semantic fallback active (deterministic validation used)"* banner whenever `semantic_provider_meta.fallback_note` is present or `matching_mode == "deterministic_fallback"`.
     - Display `free_tier_confidential_blocked` warning when `GEMINI_BILLING_TIER=free` prevents confidential policy transmission, disabling `hybrid`/`embedding_only` selection gracefully.
     - Surface `lifecycle_warnings` from `/v1/enterprise/llm-status` (e.g., `gemini-2.5-flash` December 1, 2026 deprecation toward `gemini-3.5-flash-lite`) to workspace administrators.
3. **Held-Out Quantitative Acceptance Criteria (Required After Live Gemini Run)**:
   - Execute `evaluate_e3_live_gemini.py --provider gemini --benchmark all --split all` on `E1.1`, `E3 Extended`, `E3.1 Adversarial`, and `Section 7`.
   - Confirm **`0` false equivalences**, **`0%` false confirmed coverage**, **100% unresolved conflict/waiver flagging**, **`>= 98%` citation verification pass rate**, and demonstrable held-out F1 gain over deterministic-only without excessive `429` fallback degradation.
