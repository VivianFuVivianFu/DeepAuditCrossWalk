# E3.2 Live Google Gemini & Offline Benchmark Report

> **Live Gemini Evaluation Status: `NOT RUN — CREDENTIALS UNAVAILABLE`**
>
> Neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` (nor a `.env`, `backend/.env`, or `web/.env.local` file) is present in this environment. Per E3.2 assurance rules, **zero live Gemini performance, token, cost, or latency figures have been fabricated or extrapolated**.
>
> All Config A (`disabled`), Config B (`embedding_only`, mock), and Config C (`hybrid`, mock) numbers below were directly observed against **Regulatory Pack `AU-BANKING-REG-PACK-0.1` v`0.2.0`** (`46` obligations, `17` sources, `33` controls, `55` active mappings v`1.1.0`, `0` human-approved items) using `scripts/evaluate_e3_live_gemini.py`. Machine-readable JSON output is saved in [`E32_BENCHMARK_RESULTS.json`](E32_BENCHMARK_RESULTS.json).

---

## 1. Live Credential & Pipeline Readiness Check

| Verification Check | Observed Result |
|---|---|
| `GEMINI_API_KEY` environment variable set | `False` |
| `GOOGLE_API_KEY` environment variable set | `False` |
| Workspace `.env` / `backend/.env` / `web/.env.local` present | `False` |
| Live evaluator fail-closed check (`--provider gemini` without key) | Exit code `2` — `"ERROR: Missing live Gemini credentials..."` |
| Active regulatory pack loaded by `eval_harness.py` | `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`46` obligations, `1.1.0` mappings) |
| Simulated `GoogleGeminiProvider` end-to-end transport test (`test_e32_live_gemini_validation.py`) | **Passed** (verifies model probe, header-only `x-goog-api-key`, `batchEmbedContents`, Gemini 2.5 thinking-token handling, structured JSON schema validation, 429 fallback telemetry) |

---

## 2. Offline Three-Way Results Under Pack v0.2.0 (Deterministic vs Mock-Embedding vs Mock-Hybrid)

> **Important Epistemic Distinction:**
> 1. *Finding a requirement:* `Recall@1`, `Recall@5`.
> 2. *Interpreting relationship:* `Rel Accuracy`, `Macro F1`, `False Eq`, `False Conflict`.
> 3. *Proposing document coverage:* `Proposed Coverage Cases` and `False Positive Coverage Proposals` (proposing an external link when `ground_truth_obligation_id is None`).
> 4. *Human-confirmed coverage:* `False Cov = 0` across every run because all regulatory and semantic outputs remain in `proposed`/`needs_review` (`human_approved = 0`). **Zero confirmed-coverage errors here reflects the human-review gate, NOT semantic accuracy.**

### 2.1 E1.1 Multi-Org Benchmark (`N=36`: 18 Dev + 18 Held-Out; `30` External-Obligation Queries)

| Split | Config | Recall@1 | Recall@5 | Rel Accuracy (95% CI) | Macro F1 | False Eq | False Conflict | Prop Cov (False Pos) | False Cov (Confirm) | Unresolved | Citations | Calls (Emb/LLM) | Mock Tok | Latency (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dev` | A (`disabled`) | 13/14 (92.86%) | 14/14 (100.00%) | 14/18 (77.78%, [54.79%, 91.00%]) | 74.46% | 0/18 | 0/18 | N/A* | 0/18 | 8/9 | 18/18 | 0/0 | 0 | 154.0 |
| `dev` | B (`embedding_only`, mock) | 14/14 (100.00%) | 14/14 (100.00%) | 14/18 (77.78%, [54.79%, 91.00%]) | 69.05% | 0/18 | 0/18 | N/A* | 0/18 | 6/9 | 18/18 | 21/0 | 0 | 240.7 |
| `dev` | C (`hybrid`, mock) | 14/14 (100.00%) | 14/14 (100.00%) | 17/18 (94.44%, [74.24%, 99.01%]) | 96.83% | 0/18 | 0/18 | N/A* | 0/18 | 9/9 | 18/18 | 21/49 | 19,891 | 279.5 |
| `held_out` | A (`disabled`) | 14/16 (87.50%) | 15/16 (93.75%) | 17/18 (94.44%, [74.24%, 99.01%]) | 96.83% | 0/18 | 0/18 | N/A* | 0/18 | 8/8 | 18/18 | 0/0 | 0 | 229.7 |
| `held_out` | B (`embedding_only`, mock) | 13/16 (81.25%) | 16/16 (100.00%) | 17/18 (94.44%, [74.24%, 99.01%]) | 96.83% | 0/18 | 0/18 | N/A* | 0/18 | 8/8 | 18/18 | 21/0 | 0 | 317.0 |
| `held_out` | C (`hybrid`, mock) | 13/16 (81.25%) | 16/16 (100.00%) | 17/18 (94.44%, [74.24%, 99.01%]) | 96.83% | 0/18 | 0/18 | N/A* | 0/18 | 8/8 | 18/18 | 21/45 | 18,371 | 347.0 |
| `combined` | A (`disabled`) | 27/30 (90.00%) | 29/30 (96.67%) | 31/36 (86.11%, [71.34%, 93.92%]) | 78.48% | 0/36 | 0/36 | 22 (2) | 0/36 | 16/17 | 36/36 | 0/0 | 0 | 389.6 |
| `combined` | B (`embedding_only`, mock) | 27/30 (90.00%) | 30/30 (100.00%) | 31/36 (86.11%, [71.34%, 93.92%]) | 76.71% | 0/36 | 0/36 | 24 (3) | 0/36 | 14/17 | 36/36 | 39/0 | 0 | 1119.9 |
| `combined` | C (`hybrid`, mock) | 27/30 (90.00%) | 30/30 (100.00%) | 34/36 (94.44%, [81.86%, 98.46%]) | 97.05% | 0/36 | 0/36 | 21 (0) | 0/36 | 17/17 | 36/36 | 39/94 | 38,262 | 1705.3 |
| Live Gemini | Configs B & C | **NOT RUN** | **NOT RUN** | **NOT RUN — CREDENTIALS UNAVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

*\*Split-level `False Pos Coverage Proposals` can be read per split in `E32_BENCHMARK_RESULTS.json`; combined totals reported directly above.*

### 2.2 E3 Extended Synthetic Benchmark (`N=60`: 30 Dev + 30 Held-Out; `48` External-Obligation Queries)

| Split | Config | Recall@1 | Recall@5 | Rel Accuracy (95% CI) | Macro F1 | False Eq | False Conflict | Prop Cov (False Pos) | False Cov (Confirm) | Unresolved | Citations | Calls (Emb/LLM) | Mock Tok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dev` | A (`disabled`) | 11/24 (45.83%) | 18/24 (75.00%) | 15/30 (50.00%, [33.15%, 66.85%]) | 49.77% | 0/30 | 0/30 | — | 0/30 | 10/10 | 30/30 | 0/0 | 0 |
| `dev` | B (`embedding_only`, mock) | 17/24 (70.83%) | 23/24 (95.83%) | 21/30 (70.00%, [52.12%, 83.34%]) | 75.34% | 0/30 | 0/30 | — | 0/30 | 9/10 | 30/30 | 35/0 | 0 |
| `dev` | C (`hybrid`, mock) | 17/24 (70.83%) | 23/24 (95.83%) | 24/30 (80.00%, [62.69%, 90.49%]) | 88.75% | 0/30 | 0/30 | — | 0/30 | 10/10 | 30/30 | 35/69 | 28,223 |
| `held_out` | A (`disabled`) | 16/24 (66.67%) | 22/24 (91.67%) | 14/30 (46.67%, [30.23%, 63.86%]) | 53.23% | 0/30 | 0/30 | — | 0/30 | 10/10 | 30/30 | 0/0 | 0 |
| `held_out` | B (`embedding_only`, mock) | 17/24 (70.83%) | 23/24 (95.83%) | 17/30 (56.67%, [39.20%, 72.62%]) | 68.30% | 0/30 | 0/30 | — | 0/30 | 9/10 | 30/30 | 35/0 | 0 |
| `held_out` | C (`hybrid`, mock) | 17/24 (70.83%) | 23/24 (95.83%) | 19/30 (63.33%, [45.51%, 78.13%]) | 75.48% | 0/30 | 0/30 | — | 0/30 | 10/10 | 30/30 | 35/70 | 28,491 |
| `combined` | A (`disabled`) | 27/48 (56.25%) | 40/48 (83.33%) | 29/60 (48.33%, [36.18%, 60.69%]) | 52.84% | 0/60 | 0/60 | 28 (2) | 0/60 | 20/20 | 60/60 | 0/0 | 0 |
| `combined` | B (`embedding_only`, mock) | 34/48 (70.83%) | 46/48 (95.83%) | 38/60 (63.33%, [50.68%, 74.38%]) | 71.31% | 0/60 | 0/60 | 35 (3) | 0/60 | 18/20 | 60/60 | 67/0 | 0 |
| `combined` | C (`hybrid`, mock) | 34/48 (70.83%) | 46/48 (95.83%) | 43/60 (71.67%, [59.23%, 81.49%]) | 81.40% | 0/60 | 0/60 | 32 (0) | 0/60 | 20/20 | 60/60 | 67/139 | 56,714 |
| Live Gemini | Configs B & C | **NOT RUN** | **NOT RUN** | **NOT RUN — CREDENTIALS UNAVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

### 2.3 E3.1 Adversarial Calibration Benchmark (`N=24`: 12 Dev + 12 Held-Out; `18` Queries, `3` Multi-Obligation)

| Split | Config | Recall@1 | Recall@5 | Multi-Ob (Ret/Dec/Tot) | Rel Accuracy (95% CI) | Macro F1 | False Eq | Prop Cov (False Pos) | False Cov | Unresolved | Citations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `dev` | A (`disabled`) | 9/9 (100.00%) | 9/9 (100.00%) | 2/0/2 | 8/12 (66.67%) | 50.00% | 0/12 | — | 0/12 | 5/8 | 12/12 |
| `dev` | B (`embedding_only`, mock) | 7/9 (77.78%) | 8/9 (88.89%) | 2/2/2 | 8/12 (66.67%) | 50.00% | 0/12 | — | 0/12 | 5/8 | 12/12 |
| `dev` | C (`hybrid`, mock) | 7/9 (77.78%) | 8/9 (88.89%) | 2/2/2 | 9/12 (75.00%) | 63.54% | 0/12 | — | 0/12 | 8/8 | 12/12 |
| `held_out` | A (`disabled`) | 8/9 (88.89%) | 9/9 (100.00%) | 1/1/1 | 5/12 (41.67%) | 41.43% | 0/12 | — | 0/12 | 6/7 | 12/12 |
| `held_out` | B (`embedding_only`, mock) | 6/9 (66.67%) | 9/9 (100.00%) | 1/1/1 | 6/12 (50.00%) | 43.81% | 0/12 | — | 0/12 | 6/7 | 12/12 |
| `held_out` | C (`hybrid`, mock) | 6/9 (66.67%) | 9/9 (100.00%) | 1/1/1 | 7/12 (58.33%) | 59.05% | 0/12 | — | 0/12 | 7/7 | 12/12 |
| `combined` | A (`disabled`) | 17/18 (94.44%) | 18/18 (100.00%) | 3/1/3 | 13/24 (54.17%) | 49.52% | 0/24 | 13 (2) | 0/24 | 11/15 | 24/24 |
| `combined` | B (`embedding_only`, mock) | 13/18 (72.22%) | 17/18 (94.44%) | 3/3/3 | 14/24 (58.33%) | 50.71% | 0/24 | 13 (2) | 0/24 | 11/15 | 24/24 |
| `combined` | C (`hybrid`, mock) | 13/18 (72.22%) | 17/18 (94.44%) | 3/3/3 | 16/24 (66.67%) | 64.24% | 0/24 | 11 (0) | 0/24 | 15/15 | 24/24 |
| Live Gemini | Configs B & C | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN — CREDENTIALS UNAVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A |

### 2.4 NEW E3.2 Independently Labelled Uncontaminated Holdout (`N=18`, Aligned to Pack v0.2.0; `15` Queries, `1` Multi-Obligation)

| Config | Recall@1 | Recall@5 | Multi-Ob (Ret/Dec/Tot) | Rel Accuracy (95% CI) | Macro F1 | False Eq | False Conflict | Prop Cov (False Pos) | False Cov (Confirm) | Unresolved | Citations | Calls (Emb/LLM) | Latency (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (`disabled`) | 7/15 (46.67%) | 10/15 (66.67%) | 1/0/1 | 8/18 (44.44%, [24.56%, 66.28%]) | 48.57% | 0/18 | 1/18 | 5 (0) | 0/18 | 12/13 | 18/18 | 0/0 | 499.3 |
| B (`embedding_only`, mock) | 9/15 (60.00%) | 11/15 (73.33%) | 1/1/1 | 10/18 (55.56%, [33.72%, 75.44%]) | 48.64% | 0/18 | 1/18 | 10 (2) | 0/18 | 9/13 | 18/18 | 23/0 | 721.6 |
| C (`hybrid`, mock) | 9/15 (60.00%) | 11/15 (73.33%) | 1/1/1 | 11/18 (61.11%, [38.62%, 79.69%]) | 58.84% | 0/18 | 1/18 | 9 (1) | 0/18 | 13/13 | 18/18 | 23/44 | 892.7 |
| Live Gemini (`B` & `C`) | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN — CREDENTIALS UNAVAILABLE** | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

### 2.5 Accuracy by Obligation Type (Authority Layer) — Combined Offline Results Across Datasets

| Dataset | Config | `binding` | `enforceable_guidance` | `guidance` | `voluntary` | `unmapped_or_enterprise` |
|---|---|---:|---:|---:|---:|---:|
| `e11` (N=36) | A (`disabled`) | 19/22 | 1/1 | 7/9 | N/A | 4/4 |
| `e11` (N=36) | C (`hybrid`, mock) | 20/22 | 1/1 | 7/7 | N/A | 6/6 |
| `e3` (N=60) | A (`disabled`) | 16/35 | 0/2 | 6/14 | N/A | 7/9 |
| `e3` (N=60) | C (`hybrid`, mock) | 22/34 | 0/2 | 9/12 | N/A | 12/12 |
| `e31` (N=24) | A (`disabled`) | 6/10 | 1/2 | 5/10 | N/A | 1/2 |
| `e31` (N=24) | C (`hybrid`, mock) | 6/11 | 2/3 | 5/7 | N/A | 3/3 |
| `e32` (N=18, uncontaminated) | A (`disabled`) | 3/8 | 0/3 | 0/2 | N/A | 5/5 |
| `e32` (N=18, uncontaminated) | C (`hybrid`, mock) | 5/9 | 1/4 | 1/1 | N/A | 4/4 |

### 2.6 Questionnaire Candidate Retrieval (`N=22` In-Scope Queries: 18 from E3 + 4 from E3.2 Holdout)

| Config | Dev R@1 | Dev R@3 | Holdout R@1 | Holdout R@3 | Confirmed Covered | Calls (Emb/LLM) | Latency (ms) |
|---|---|---|---|---|---|---|---|
| A (`disabled`, lexical) | 5/9 | 7/9 | 11/13 | 12/13 | 0 | 0/0 | 64.6 |
| B (`embedding_only`, mock) | 7/9 | 9/9 | 11/13 | 11/13 | 0 | 26/0 | 158.2 |
| C (`hybrid`, mock) | 7/9 | 9/9 | 11/13 | 11/13 | 0 | 26/69 | 254.1 |
| Live Gemini (`B` & `C`) | **NOT RUN** | **NOT RUN** | **NOT RUN** | **NOT RUN — CREDENTIALS UNAVAILABLE** | N/A | N/A | N/A |

---

## 3. Reproducible Operator Commands for Live Gemini Validation

```powershell
# 1. Verify offline mock & deterministic baselines cleanly (no API key required)
$env:PYTHONPATH = "backend;backend/tests"
.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all --output-json E32_BENCHMARK_RESULTS.json

# 2. Execute live Gemini 3-way evaluation once external API credentials are set
#    (uses synthetic DataClassification.PUBLIC_OR_SYNTHETIC benchmarks only; never commit keys)
$env:GEMINI_API_KEY = "<operator-supplied-key>"
$env:PYTHONPATH = "backend;backend/tests"
.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py `
  --provider gemini `
  --probe-models `
  --benchmark all `
  --split all `
  --model gemini-2.5-flash `
  --embedding-model gemini-embedding-001 `
  --billing-tier free `
  --rpm-delay 4.2 `
  --output-json live_gemini_e32_results.json `
  --output-md live_gemini_e32_report.md
```
