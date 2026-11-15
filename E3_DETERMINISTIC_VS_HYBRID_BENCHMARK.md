# E3 Deterministic vs. Hybrid Benchmark Report

> **Important Scope Notice**: All quantitative results below were produced by running `pytest backend/tests/test_e3_semantic_matching.py -v -s` (with `DeterministicMockSemanticProvider` supplying semantic similarity vectors and structured reasoning analyses under Stage C deterministic validation). They measure pipeline retrieval, veto discipline, safety invariants, and mock semantic disambiguation behaviour in this repository — **not** live production accuracy of hosted Gemini or GPT models on unseen customer documents. Confidence intervals are 95% Wilson score intervals.

---

## 1. Benchmark Configurations Compared

- **Config A (`disabled` / Deterministic Only)**: E1.1 baseline deterministic lexical/facet candidate retrieval + deterministic relationship validation. (`emb_calls=0`, `llm_calls=0`)
- **Config B (`embedding_only` + Deterministic)**: Stage A embedding top-$k$ augmentation + deterministic relationship validation only. (`llm_calls=0`)
- **Config C (`hybrid`: Embedding + LLM + Stage C Deterministic Validation)**: Stage A embedding retrieval + Stage B structured semantic analysis + Stage C deterministic veto gate (caps unproven paraphrases at `PARTIALLY_OVERLAPPING` + `NEEDS_REVIEW`, enforces conflicts).

---

## 2. Benchmark 1 — E1.1 Multi-Org Synthetic Benchmark ($N = 36$ Clauses, 30 Retrieval Queries, 17 Expecting Human Resolution)

Observed run metrics from `test_e3_08_e11_benchmark_comparison`:

| Metric | Config A (`disabled`) | Config B (`embedding_only`) | Config C (`hybrid`) |
|---|---|---|---|
| Candidate Recall@1 | `27/30` (`90.00%`, 95% CI `[74.38%, 96.54%]`) | `27/30` (`90.00%`, 95% CI `[74.38%, 96.54%]`) | `27/30` (`90.00%`, 95% CI `[74.38%, 96.54%]`) |
| Candidate Recall@5 | `29/30` (`96.67%`, 95% CI `[83.33%, 99.41%]`) | **`30/30` (`100.00%`, 95% CI `[88.65%, 100.00%]`)** | **`30/30` (`100.00%`, 95% CI `[88.65%, 100.00%]`)** |
| Relationship Classification Accuracy | `32/36` (`88.89%`, 95% CI `[74.69%, 95.59%]`) | `32/36` (`88.89%`, 95% CI `[74.69%, 95.59%]`) | **`35/36` (`97.22%`, 95% CI `[85.83%, 99.51%]`)** |
| Macro Precision / Recall / Macro-F1 | `79.58% / 80.38% / 79.82%` | `83.33% / 77.78% / 78.01%` | **`98.61% / 98.61% / 98.53%`** |
| Weighted F1 | `88.04%` | `87.14%` | **`97.22%`** |
| False Equivalence Rate | `0/36` (`0.00%`, 95% CI `[0.00%, 9.64%]`) | `0/36` (`0.00%`) | `0/36` (`0.00%`) |
| False Confirmed Coverage Rate | `0/36` | `0/36` | `0/36` |
| False Conflict Rate | `0/36` | `0/36` | `0/36` |
| Unresolved Relationship Detection | `16/17` (`94.12%`, 95% CI `[73.02%, 98.95%]`) | `14/17` (`82.35%`, 95% CI `[58.97%, 93.81%]`) | **`17/17` (`100.00%`, 95% CI `[81.57%, 100.00%]`)** |
| Citation Grounding Accuracy | `36/36` (`100.00%`, 95% CI `[90.36%, 100.00%]`) | `36/36` (`100.00%`) | `36/36` (`100.00%`) |
| Latency / API Calls | `351.21 ms` (`0` emb, `0` llm) | `524.31 ms` (`41` emb / `84` texts, `0` llm) | `496.60 ms` (`41` emb / `84` texts, `67` llm, `0` fallbacks) |

### Diagnostic E1.1 Analysis
- Config C resolved 3 of the 4 Config A misclassifications (`DEV-PMC-14` `unmapped -> partially_overlapping`, `DEV-PMC-15` `partially_overlapping -> additional`, `DEV-PMC-18` `partially_overlapping -> unmapped`) while preserving `DEV-PMC-17`, `HO-ADN-13`, and `HO-ADN-14`.
- The single remaining miss (`DEV-PMC-13`: expected `EQUIVALENT`, output `PARTIALLY_OVERLAPPING`) is an intentional **Stage C safety trade-off**: deterministic canonical facet extraction did not prove all obligation facets on that paraphrased clause, so Stage C capped it at `PARTIALLY_OVERLAPPING` (`needs_review`) rather than risking a False Equivalence.

---

## 3. Benchmark 2 — E3 Extended 60-Clause Multi-Org Benchmark (Dev $N = 30$ + Locked Holdout $N = 30$, 48 Retrieval Queries, 20 Expecting Human Resolution)

Dataset: [tests/e3_benchmark_dataset.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/e3_benchmark_dataset.py) (`E3_EXTENDED_CLAUSES` across 3 Dev and 3 unseen Holdout banking organisations in PDF/DOCX/TXT formats, designed to test paraphrased phrasing without keyword overlap, multi-obligation clauses, internal telemetry distractors, and conflicts).

### 3.1 Combined ($N = 60$, 48 Queries)

| Metric | Config A (`disabled`) | Config B (`embedding_only`) | Config C (`hybrid`) |
|---|---|---|---|
| Candidate Recall@1 | `26/48` (`54.17%`, 95% CI `[40.29%, 67.42%]`) | **`34/48` (`70.83%`, 95% CI `[56.82%, 81.76%]`)** | **`34/48` (`70.83%`, 95% CI `[56.82%, 81.76%]`)** |
| Candidate Recall@5 | `40/48` (`83.33%`, 95% CI `[70.42%, 91.30%]`) | **`46/48` (`95.83%`, 95% CI `[86.02%, 98.85%]`)** | **`46/48` (`95.83%`, 95% CI `[86.02%, 98.85%]`)** |
| Relationship Accuracy | `27/60` (`45.00%`, 95% CI `[33.09%, 57.51%]`) | `31/60` (`51.67%`, 95% CI `[39.31%, 63.82%]`) | **`35/60` (`58.33%`, 95% CI `[45.73%, 69.94%]`)** |
| Macro F1 | `48.29%` | `51.21%` | **`62.96%`** |
| False Equivalence / Coverage / Conflict | `0/60` / `0/60` / `0/60` | `0/60` / `0/60` / `0/60` | **`0/60` / `0/60` / `0/60`** |
| Unresolved Detection | `19/20` (`95.00%`) | `15/20` (`75.00%`) | **`20/20` (`100.00%`, 95% CI `[83.89%, 100.00%]`)** |
| Citation Accuracy | `60/60` (`100.00%`) | `60/60` (`100.00%`) | `60/60` (`100.00%`) |
| Latency / Calls | `635.94 ms` (`0` emb, `0` llm) | `784.45 ms` (`69` emb / `112` texts) | `923.05 ms` (`69` emb / `112` texts, `105` llm) |

### 3.2 Dev ($N = 30$, 24 Queries) vs. Locked Holdout ($N = 30$, 24 Queries)

| Split | Metric | Config A (`disabled`) | Config B (`embedding_only`) | Config C (`hybrid`) |
|---|---|---|---|---|
| **Dev** | Recall@1 | `11/24` (`45.83%`) | `17/24` (`70.83%`) | `17/24` (`70.83%`) |
| **Dev** | Recall@5 | `18/24` (`75.00%`) | **`23/24` (`95.83%`)** | **`23/24` (`95.83%`)** |
| **Dev** | Relationship Accuracy | `14/30` (`46.67%`) | `18/30` (`60.00%`) | **`20/30` (`66.67%`)** (Macro-F1 `72.02%`) |
| **Holdout** | Recall@1 | `15/24` (`62.50%`) | `17/24` (`70.83%`) | `17/24` (`70.83%`) |
| **Holdout** | Recall@5 | `22/24` (`91.67%`) | **`23/24` (`95.83%`)** | **`23/24` (`95.83%`)** |
| **Holdout** | Relationship Accuracy | `13/30` (`43.33%`) | `13/30` (`43.33%`) | **`15/30` (`50.00%`)** (Macro-F1 `52.54%`, Unresolved `10/10 = 100%`, FalseEq `0/30`) |

### Key Finding on Config B vs. Config C (Why Embeddings Alone Underperformed on Unresolved Detection)
- Adding embeddings alone (Config B) improved Candidate Recall@1 (`54.17% -> 70.83%`) and Recall@5 (`83.33% -> 95.83%`), **but dropped Unresolved Detection (`94.12% -> 82.35%` on E1.1; `95.00% -> 75.00%` on E3 Extended)** because top-$k$ similarity pulled extra near-neighbor candidates into deterministic matching without semantic disambiguation.
- **Config C (Hybrid Embedding + LLM + Stage C)** solved that regression, lifting Unresolved Detection to **`17/17` (`100.00%`)** on E1.1 and **`20/20` (`100.00%`)** on E3 Extended while preserving the Stage A Recall@5 gains (`100.00%` / `95.83%`).
- **Why E3 Extended Relationship Accuracy is `58.33%` (and why that is honest & desirable)**: The E3 extended suite intentionally contains paraphrased `EQUIVALENT` clauses without canonical regulatory wording. Stage C **refuses to promote an LLM claim to `EQUIVALENT` without deterministic canonical facet proof**, instead routing those clauses to `PARTIALLY_OVERLAPPING` + `NEEDS_REVIEW`. That keeps **False Equivalence = `0/60` (`0.00%`)** while surfacing the right candidate obligations for human confirmation.

---

## 4. Benchmark 3 — Section 7 Questionnaire-to-Requirement Mapping Harness ($N = 20$: 18 In-Scope + 2 Out-of-Scope Distractors)

Observed from `test_e3_10_section7_questionnaire_mapping_benchmark`:

| Metric | Config A (Lexical Only) | Config B (Embedding Top-K) | Config C (Hybrid Embedding + LLM) |
|---|---|---|---|
| Combined Recall@1 | `13/18` (`72.22%`, 95% CI `[49.13%, 87.50%]`) | `14/18` (`77.78%`, 95% CI `[54.79%, 91.00%]`) | `14/18` (`77.78%`, 95% CI `[54.79%, 91.00%]`) |
| Combined Recall@3 | `16/18` (`88.89%`, 95% CI `[67.20%, 96.90%]`) | `16/18` (`88.89%`, 95% CI `[67.20%, 96.90%]`) | **`17/18` (`94.44%`, 95% CI `[74.24%, 99.01%]`)** |
| Dev Recall@1 / Recall@3 | `6/9` / `8/9` | `7/9` / `9/9` | `7/9` / `9/9` |
| Locked Holdout Recall@1 / Recall@3 | `7/9` / `8/9` | `7/9` / `7/9` | `7/9` / `8/9` |
| Latency | `15.25 ms` | `38.44 ms` | `36.91 ms` |
| Auto-Confirmed Coverage | **`0 (0.0%)`** | **`0 (0.0%)`** | **`0 (0.0%)`** |

---

## 5. Release Readiness Verdict

- **Recommendation**: Ship E3 as an **opt-in** feature (`SEMANTIC_MATCHING_ENABLED=false` by default).
- **Rationale**:
  1. Zero regressions across existing deterministic pipelines (`269 passed, 4 skipped` in backend tests; `78 passed` in frontend Vitest; PostgreSQL 16 RLS tests green).
  2. Safety invariants (`0` false equivalences, `0` auto-confirmed coverage, `0` secret leaks, fail-closed confidential free-tier block) held across all automated and fault-injection suites.
  3. Real-world hosted Gemini latency, token cost, and live paraphrased recall still require live paid-tier validation (`test_e3_07_opt_in_live_gemini_smoke` + pilot review) before any deployment enables `SEMANTIC_MATCHING_ENABLED=true` by default.
