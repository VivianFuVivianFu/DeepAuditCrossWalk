# E3.1 Deterministic vs Hybrid Matching Trade-Off Comparison

> **Scope Note**: Live Gemini execution is `NOT RUN — CREDENTIALS UNAVAILABLE`. Figures below compare measured Config A (`disabled` — deterministic only), Config B (`embedding_only`, offline mock), and Config C (`hybrid`, offline mock) across identical datasets on commit `feat/e31-live-gemini-calibration`, alongside documented operational behaviour for live Gemini (`gemini-embedding-001` + `gemini-2.5-flash`).

---

## 1. Side-by-Side Comparison (`mock` Offline Measurements)

| Dimension | Config A (`disabled` / Deterministic) | Config B (`embedding_only` + Deterministic) | Config C (`hybrid` Mock Stage B + Deterministic Stage C) | Live Gemini (`hybrid`, `NOT RUN — CREDENTIALS UNAVAILABLE`) |
|---|---|---|---|---|
| **E1.1 (`N=36`) Combined Accuracy** | `32/36 (88.89%)` | `32/36 (88.89%)` | **`35/36 (97.22%, MacroF1=98.53%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **E3 Extended (`N=60`) Combined** | `29/60 (48.33%)` | `38/60 (63.33%)` | **`43/60 (71.67%, MacroF1=81.40%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **E3 Extended Held-Out (`N=30`)** | `14/30 (46.67%)` | `17/30 (56.67%)` | **`19/30 (63.33%, MacroF1=75.48%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **E3 Extended Recall@5** | `40/48 (83.33%)` | **`46/48 (95.83%)`** | **`46/48 (95.83%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **E3.1 Adversarial (`N=24`) Combined** | `13/24 (54.17%)` | `14/24 (58.33%)` | **`16/24 (66.67%, MacroF1=64.24%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **E3.1 Multi-Obligation Decision Recall** | `0/3 (0.00%)` | **`3/3 (100.00%)`** | **`3/3 (100.00%)`** | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **Unresolved Human-Review Detection** | `16/17` (`e11`), `20/20` (`e3`), `11/15` (`e31`) | `14/17` (`e11`), `18/20` (`e3`), `11/15` (`e31`) | **`17/17`, `20/20`, `15/15` (`100%`)** | Enforced by Stage C + D |
| **False Equivalence / False Coverage** | **`0` / `0`** across all `120` clauses | **`0` / `0`** across all `120` clauses | **`0` / `0`** across all `120` clauses | Enforced by Stage C Veto + `PROPOSED`/`NEEDS_REVIEW` |
| **Section 7 Questionnaire (Combined R@3)** | `16/18`, `Confirmed=0` | `16/18`, `Confirmed=0` | `16/18` (`9/9` Dev, `7/9` HO), `Confirmed=0` | `NOT RUN — CREDENTIALS UNAVAILABLE` |
| **Network Calls & External Dependency** | `0` calls (`<0.8s` full `N=60`) | Embeddings only (`28–67` calls) | Embeddings + Stage B LLM (`66–139` calls) | Subject to Gemini 15 RPM free-tier pacing (`--rpm-delay 4.2`) |

---

## 2. Operational, Cost & Resilience Characteristics

1. **Zero-Regression Safety Floor**:
   - Stage C deterministic checks (`validate_candidate_relationship`) retain unconditional veto power over Stage B LLM proposals on scope, numeric thresholds/operators, cross-currency comparisons (`EUR`, `USD`, `NZD` vs `AUD`), pre- vs post-execution approval timing, authority roles, exemptions, and ambiguous clauses (`Schedule`/`Appendix`/`Annex`/`Exhibit`).
   - Regardless of matching mode, reconciled decisions always emit `decision_status` in `{proposed, needs_review}` and never auto-approve coverage.
2. **Latency & Free-Tier Rate Limits**:
   - Under `DeterministicMockSemanticProvider`, hybrid execution across `N=60` clauses completes in `~1.24s` (`28–67` embedding batches, `139` reasoning calls, `56,714` mock-estimated tokens).
   - Under live Gemini Free Tier (`15 RPM`), sequential execution requires `rpm_min_interval_seconds >= 4.0` (`--rpm-delay 4.2`), meaning a full `N=60` sweep with ~206 API calls takes ~14 minutes uncached vs <1s offline; therefore CI always defaults to `mock`/`disabled`, with live Gemini sweeps run asynchronously by operators via `scripts/evaluate_e3_live_gemini.py`.
3. **Resilient Fallback Behavior**:
   - On HTTP `429`, socket timeouts, truncated `finishReason=MAX_TOKENS` output, or `CitationVerificationError`, Stage B cleanly falls back per-candidate (`matching_mode="deterministic_fallback"`) while `ConfidentialityPolicyError` (`HTTP 403`) and `ProviderConfigurationError` (`HTTP 503`) fail closed rather than downgrading security boundaries.

---

## 3. When to Choose Each Mode

| Workload / Environment | Recommended Mode | Rationale |
|---|---|---|
| Production confidential tenant policies under `GEMINI_BILLING_TIER=free` | **`disabled` (`deterministic_only`)** | Fail-closed confidentiality blocks free-tier Gemini (`HTTP 403`); deterministic preserves `0` false equivalence and sub-second execution. |
| Cost-conscious / air-gapped candidate discovery | **`embedding_only`** (OpenAI-compatible private VPC or paid Gemini) | Boosts `e3` Recall@5 (`83.33% -> 95.83%`) and multi-obligation recall (`0/3 -> 3/3`) with no per-candidate generative LLM cost. |
| Opt-in internal evaluation / paid enterprise private VPC or paid Gemini | **`hybrid`** | Highest accuracy and unresolved flagging when human reviewers remain mandatory in Stage D and real live calibration passes release gates. |
