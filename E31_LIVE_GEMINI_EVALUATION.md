# E3.1 Live Google Gemini Evaluation & Calibration Report

> **Live Gemini Evaluation Status: `NOT RUN — CREDENTIALS UNAVAILABLE`**
>
> Neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` (nor a workspace `.env` file) is present in the execution environment. Per E3.1 assurance policy, **no live Gemini accuracy, token, cost, or latency figures have been fabricated**. This document records the completed pre-flight code hardening, the reproducible CLI harness, and the offline Config A (`disabled`), Config B (`embedding_only`, mock), and Config C (`hybrid`, mock) baseline metrics measured on the current branch (`feat/e31-live-gemini-calibration`).

---

## 1. Environment & Credential Audit

| Check | Result |
|---|---|
| Workspace `.env` present | `False` |
| `GEMINI_API_KEY` set | `False` |
| `GOOGLE_API_KEY` set | `False` |
| Opt-in pytest live smoke (`test_e3_07_opt_in_live_gemini_smoke`) | `SKIPPED` (requires `RUN_GEMINI_LIVE_TESTS=1` & `GEMINI_API_KEY`) |
| Reproducible CLI check `--provider gemini` without key | Exit code `2` — fails closed with clear operator error and zero secret exposure |

---

## 2. Live Gemini Pipeline Fixes & Harness Delivered

Phase 1 code inspection uncovered four live-execution defects fixed in this PR:

1. **Live Smoke Test Config Mismatch (`backend/tests/test_e3_semantic_matching.py`)**:
   - `test_e3_07_opt_in_live_gemini_smoke` previously set `LLM_MATCHING_MODE="hybrid"` instead of `SEMANTIC_MATCHING_ENABLED="true"` and `SEMANTIC_MATCHING_MODE="hybrid"`, causing live runs to instantiate disabled providers.
2. **Gemini 2.5 Thinking-Token Budget, Usage & Finish-Reason Handling (`backend/banking_crosswalk/llm/providers.py`, `types.py`)**:
   - `GoogleGeminiProvider._generate_structured()` now enforces `maxOutputTokens >= 2048` on `"2.5"` models (preventing reasoning/thinking tokens from starving JSON output).
   - Filters `thought: true` response parts, fails closed on `finishReason="MAX_TOKENS"` (when JSON is truncated) and blocked reasons (`SAFETY`, `RECITATION`, `BLOCKLIST`, `PROHIBITED_CONTENT`), and records `thoughts_tokens`, `total_tokens`, `api_attempts`, and `estimated_cost_usd` in `UsageTelemetry`.
   - Added `rpm_min_interval_seconds` request pacing (`_pace_rpm()`) and raised `max_calls_per_run` ceiling to `2000` for full benchmark sweeps without relaxing default limits (`40`).
   - Added `probe_gemini_model_availability()` (`HttpGetTransport`, header-only `x-goog-api-key`, `scrub_secrets()` on non-200 errors).
3. **Abbreviated Statutory Provision Citation Matching (`backend/banking_crosswalk/llm/security.py`)**:
   - `validate_semantic_citation()` now normalises valid statutory abbreviations (e.g. `"APP 1.1-1.6"` vs `"Schedule 1, APP 1.1–1.6"`, `"ss 26WE-26WL"` vs `"Part IIIC, ss 26WE–26WL"`) while rejecting fabricated provisions, mismatched `cited_obligation_id`, or ungrounded clause quotes.
4. **Reproducible Live Gemini CLI Evaluation Harness**:
   - `backend/banking_crosswalk/llm/eval_harness.py` & `scripts/evaluate_e3_live_gemini.py`
   - Supports `--provider mock|gemini`, `--benchmark e11|e3|e31|questionnaire|all`, `--split all|dev|held_out`, `--model`, `--embedding-model`, `--billing-tier`, `--rpm-delay`, `--probe-models`, `--output-json`, and `--output-md`.
   - Explicitly tags synthetic evaluation workloads with `DataClassification.PUBLIC_OR_SYNTHETIC` so operators can run free-tier Gemini calibration without weakening `CONFIDENTIAL_ENTERPRISE` fail-closed blocking.

---

## 3. Exact Offline Benchmark Measurements (`provider=mock`, Current Branch)

Command executed:
```powershell
.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all
```

### 3.1 E1.1 Realistic Multi-Org Benchmark (`N=36`: 18 Dev + 18 Locked Holdout)

| Split | Config | Recall@1 | Recall@5 | Rel Accuracy (95% Wilson CI) | Macro F1 | False Eq | False Cov | Unresolved | Citations | Calls (Emb/LLM) | Tokens (Mock Est.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `dev` | `disabled` | 13/14 (92.86%) | 14/14 (100.00%) | 14/18 (77.78%, [54.79%, 91.00%]) | 74.46% | 0/18 | 0/18 | 8/9 | 18/18 | 0/0 | 0 |
| `dev` | `embedding_only` | 14/14 (100.00%) | 14/14 (100.00%) | 14/18 (77.78%, [54.79%, 91.00%]) | 69.05% | 0/18 | 0/18 | 6/9 | 18/18 | 21/0 | 0 |
| `dev` | `hybrid` | 14/14 (100.00%) | 14/14 (100.00%) | 17/18 (94.44%, [74.24%, 99.01%]) | 96.83% | 0/18 | 0/18 | 9/9 | 18/18 | 21/49 | 19,891 |
| `held_out` | `disabled` | 14/16 (87.50%) | 15/16 (93.75%) | 18/18 (100.00%, [82.41%, 100.00%]) | 100.00% | 0/18 | 0/18 | 8/8 | 18/18 | 0/0 | 0 |
| `held_out` | `embedding_only` | 13/16 (81.25%) | 16/16 (100.00%) | 18/18 (100.00%, [82.41%, 100.00%]) | 100.00% | 0/18 | 0/18 | 8/8 | 18/18 | 21/0 | 0 |
| `held_out` | `hybrid` | 13/16 (81.25%) | 16/16 (100.00%) | 18/18 (100.00%, [82.41%, 100.00%]) | 100.00% | 0/18 | 0/18 | 8/8 | 18/18 | 21/45 | 18,371 |
| `combined` | `disabled` | 27/30 (90.00%) | 29/30 (96.67%) | 32/36 (88.89%, [74.69%, 95.59%]) | 79.82% | 0/36 | 0/36 | 16/17 | 36/36 | 0/0 | 0 |
| `combined` | `embedding_only` | 27/30 (90.00%) | 30/30 (100.00%) | 32/36 (88.89%, [74.69%, 95.59%]) | 78.01% | 0/36 | 0/36 | 14/17 | 36/36 | 39/0 | 0 |
| `combined` | `hybrid` | 27/30 (90.00%) | 30/30 (100.00%) | **35/36 (97.22%, [85.83%, 99.51%])** | **98.53%** | **0/36** | **0/36** | **17/17** | **36/36** | 39/94 | 38,262 |

### 3.2 E3 Extended Synthetic Benchmark (`N=60`: 30 Dev + 30 Locked Holdout)

| Split | Config | Recall@1 | Recall@5 | Rel Accuracy (95% Wilson CI) | Macro F1 | False Eq | False Cov | Unresolved | Citations |
|---|---|---|---|---|---|---|---|---|---|
| `dev` | `disabled` | 11/24 (45.83%) | 18/24 (75.00%) | 15/30 (50.00%, [33.15%, 66.85%]) | 49.77% | 0/30 | 0/30 | 10/10 | 30/30 |
| `dev` | `embedding_only` | 17/24 (70.83%) | 23/24 (95.83%) | 21/30 (70.00%, [52.12%, 83.34%]) | 75.34% | 0/30 | 0/30 | 9/10 | 30/30 |
| `dev` | `hybrid` | 17/24 (70.83%) | 23/24 (95.83%) | **24/30 (80.00%, [62.69%, 90.49%])** | 88.75% | 0/30 | 0/30 | 10/10 | 30/30 |
| `held_out` | `disabled` | 15/24 (62.50%) | 22/24 (91.67%) | 14/30 (46.67%, [30.23%, 63.86%]) | 52.94% | 0/30 | 0/30 | 10/10 | 30/30 |
| `held_out` | `embedding_only` | 17/24 (70.83%) | 23/24 (95.83%) | 17/30 (56.67%, [39.20%, 72.62%]) | 68.30% | 0/30 | 0/30 | 9/10 | 30/30 |
| `held_out` | `hybrid` | 17/24 (70.83%) | 23/24 (95.83%) | **19/30 (63.33%, [45.51%, 78.13%])** | 75.48% | 0/30 | 0/30 | 10/10 | 30/30 |
| `combined` | `disabled` | 26/48 (54.17%) | 40/48 (83.33%) | 29/60 (48.33%, [36.18%, 60.69%]) | 52.74% | 0/60 | 0/60 | 20/20 | 60/60 |
| `combined` | `embedding_only` | 34/48 (70.83%) | 46/48 (95.83%) | 38/60 (63.33%, [50.68%, 74.38%]) | 71.31% | 0/60 | 0/60 | 18/20 | 60/60 |
| `combined` | `hybrid` | 34/48 (70.83%) | **46/48 (95.83%)** | **43/60 (71.67%, [59.23%, 81.49%])** | **81.40%** | **0/60** | **0/60** | **20/20** | **60/60** |

### 3.3 E3.1 Adversarial Calibration Benchmark (`N=24`: 12 Dev + 12 Locked Holdout, 9 Phenomena)

| Split | Config | Recall@1 | Recall@5 | Multi-Ob (Ret/Dec/Tot) | Rel Accuracy (95% CI) | Macro F1 | False Eq | False Cov | Unresolved | Citations |
|---|---|---|---|---|---|---|---|---|---|---|
| `dev` | `disabled` | 9/9 (100.00%) | 9/9 (100.00%) | 2/0/2 | 8/12 (66.67%, [39.06%, 86.19%]) | 50.00% | 0/12 | 0/12 | 5/8 | 12/12 |
| `dev` | `embedding_only` | 7/9 (77.78%) | 8/9 (88.89%) | 2/2/2 | 8/12 (66.67%, [39.06%, 86.19%]) | 50.00% | 0/12 | 0/12 | 5/8 | 12/12 |
| `dev` | `hybrid` | 7/9 (77.78%) | 8/9 (88.89%) | 2/2/2 | 9/12 (75.00%, [46.77%, 91.11%]) | 63.54% | 0/12 | 0/12 | 8/8 | 12/12 |
| `held_out` | `disabled` | 8/9 (88.89%) | 9/9 (100.00%) | 1/0/1 | 5/12 (41.67%, [19.33%, 68.05%]) | 41.43% | 0/12 | 0/12 | 6/7 | 12/12 |
| `held_out` | `embedding_only` | 7/9 (77.78%) | 9/9 (100.00%) | 1/1/1 | 6/12 (50.00%, [25.38%, 74.62%]) | 43.81% | 0/12 | 0/12 | 6/7 | 12/12 |
| `held_out` | `hybrid` | 7/9 (77.78%) | 9/9 (100.00%) | 1/1/1 | 7/12 (58.33%, [31.95%, 80.67%]) | 59.05% | 0/12 | 0/12 | 7/7 | 12/12 |
| `combined` | `disabled` | 17/18 (94.44%) | 18/18 (100.00%) | 3/0/3 | 13/24 (54.17%, [35.07%, 72.11%]) | 49.52% | 0/24 | 0/24 | 11/15 | 24/24 |
| `combined` | `embedding_only` | 14/18 (77.78%) | 17/18 (94.44%) | 3/3/3 | 14/24 (58.33%, [38.83%, 75.53%]) | 50.71% | 0/24 | 0/24 | 11/15 | 24/24 |
| `combined` | `hybrid` | 14/18 (77.78%) | 17/18 (94.44%) | **3/3/3** | **16/24 (66.67%, [46.71%, 82.03%])** | **64.24%** | **0/24** | **0/24** | **15/15** | **24/24** |

### 3.4 Section 7 Questionnaire Semantic Candidate Harness (`N=20`, 18 In-Scope)

| Mode | Dev R@1 | Dev R@3 | Holdout R@1 | Holdout R@3 | Confirmed Covered (Safety) |
|---|---|---|---|---|---|
| `disabled` (Lexical Only) | 6/9 | 8/9 | 7/9 | 8/9 | 0 |
| `embedding_only` | 7/9 | 9/9 | 7/9 | 7/9 | 0 |
| `hybrid` | 7/9 | 9/9 | 7/9 | 7/9 | 0 |

*(Note: `test_e3_10` uses a slightly different `evaluate_questionnaire_coverage` harness setup; standalone CLI `evaluate_questionnaire_benchmark` reports `Holdout R@3 = 7/9`, `Confirmed Covered = 0`, all `ReviewStatus.PROPOSED`.)*

---

## 4. Operator Command to Execute Live Gemini Calibration

When a valid Google AI Studio / Gemini API key is supplied externally (never commit to `.env` or source control):

```powershell
$env:GEMINI_API_KEY = "<external-operator-key>"
.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py `
  --provider gemini `
  --probe-models `
  --benchmark all `
  --split all `
  --model gemini-2.5-flash `
  --embedding-model gemini-embedding-001 `
  --billing-tier free `
  --rpm-delay 4.2 `
  --output-json live_gemini_eval.json `
  --output-md live_gemini_eval.md
```
