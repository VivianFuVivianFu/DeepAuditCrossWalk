# E3.2 Release Readiness Decision

**Decision Date:** `2026-11-16` | **Regulatory Pack:** `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`46` obligations, `0` human-approved) | **Branch:** `feat/e32-live-gemini-accuracy-validation`

---

## 1. Pre-Defined Release Gates vs. Observed E3.2 Evidence

| Release Gate | Required Criterion | Observed Result | Gate Status |
|---|---|---|---|
| **Gate 1 — Live Model Verification** | Real Gemini Config B & C evaluated via `--provider gemini` on held-out suites (`e11`, `e3`, `e31`, `e32`, `questionnaire`) with traceable token/latency telemetry | **`NOT RUN — CREDENTIALS UNAVAILABLE`** (`GEMINI_API_KEY` and `GOOGLE_API_KEY` unset) | **FAILED / BLOCKED** |
| **Gate 2 — Neural vs. Deterministic Lift** | Real Gemini outperforms deterministic-only Config A on uncontaminated holdout (`e32`) without tuning against held-out answers | Only offline mock ran: `e32` Accuracy A=`8/18 (44.44%)` -> C=`11/18 (61.11%)`; real Gemini accuracy remains **unknown** | **FAILED (Insufficient Evidence)** |
| **Gate 3 — Safety & Zero False Coverage** | `0` false equivalence, `0` auto-confirmed coverage (`False Cov = 0`), bounded false-positive coverage proposals | `False Eq = 0/138`, `False Cov = 0/138`; **however**, uncontaminated `e32` mock exhibited `1/18` false-positive proposal (`E32-HO-18`) and `2/18` in embedding-only (`Config B`) | **CONDITIONAL (Needs Live Check)** |
| **Gate 4 — Benchmark Independence** | Uncontaminated holdout exists free of mock cue overfitting | `E32_INDEPENDENT_HOLDOUT` (`N=18` + `4` questionnaire cases) created & verified without mock tuning | **PASSED** |
| **Gate 5 — Security, Confidentiality & Fallbacks** | Free tier blocks `CONFIDENTIAL_ENTERPRISE`; deterministic fallback on 429/timeout/malformed JSON; zero leaked secrets | Verified via `test_e32_live_gemini_validation.py`, `test_e3_semantic_matching.py`, `check_secrets.py`, CodeQL | **PASSED** |
| **Gate 6 — Human Legal Review Gate** | Regulatory records remain `proposed` until qualified legal review | `human_approved = 0` across all `17` sources, `46` obligations, `55` mappings | **PASSED (Retained)** |

---

## 2. Final Release Decision

### **Decision: `NO-GO` for Customer-Facing Live Gemini / Hybrid Semantic Matching**

**Per Phase 8 Policy:** Because real Gemini accuracy, latency, token consumption, and failure modes could not be measured (`NOT RUN — CREDENTIALS UNAVAILABLE`), live Gemini has **not** demonstrated improvement over the deterministic baseline:
1. **Default production mode MUST remain Deterministic-Only (`SEMANTIC_MATCHING_ENABLED=false`)** — zero LLM credentials required, reproducible behaviour, zero external data egress risk.
2. **Do NOT enable customer-facing Hybrid Semantic Matching or anonymous public trials.**
3. **Permitted Scope on Merge:** Repository code on `main` is safe **strictly** as:
   - Offline deterministic governance engine (default)
   - Security-hardened, opt-in internal/synthetic operator harness (`scripts/evaluate_e3_live_gemini.py --provider gemini --probe-models --benchmark e32 --split held_out`) for future credentialed evaluation.

---

## 3. Conditions Required to Re-Evaluate Toward `CONDITIONAL GO` / `GO`

1. Supply an isolated test project `GEMINI_API_KEY` externally and execute `scripts/evaluate_e3_live_gemini.py --provider gemini --probe-models --benchmark all --split all` (or targeted `held_out` runs) capturing live tokens, `estimated_cost_usd`, latency, and HTTP 429 rates.
2. Verify real Gemini Config C improves `E32_INDEPENDENT_HOLDOUT` and `E3`/`E3.1` held-out Macro F1 over Config A with `0` false equivalence and `0` unsafe false-positive coverage proposals on out-of-domain text (`E32-HO-18`).
3. Fix the architectural `Annex III` collision in `reconciliation.py` (`E32-HO-04`), Australian `"Annexure"` omission (`E31-HO-10` / `E32-HO-16`), and permissive negation pattern (`E32-HO-05`) on `dev`/general rules before a subsequent live validation run.
4. For any future confidential customer use, require **`GEMINI_BILLING_TIER=paid`** (or private VPC `openai_compatible` deployment) and qualified human legal sign-off on active regulatory library records (`E4_LEGAL_REVIEW_REGISTER.csv`).
