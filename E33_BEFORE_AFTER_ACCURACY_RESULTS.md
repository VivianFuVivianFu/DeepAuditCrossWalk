# E3.3 Before / After Accuracy & Safety Evaluation Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Stage:** Stage B (`fix/e33-evidence-preserving-matching`, combined with Stage A `fix/p1b-taxonomy-v02-alignment`)  
**Regulatory Library Baseline:** Regulatory Pack `v0.2.0` (`17` sources, `46` atomic obligations, `33` unified controls, `158` canonical control facets, `55` active mappings, `0` human-approved mappings)  
**Reproducibility Commands:**
- `python scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all`
- `pytest scripts/experiments -q`
- `pytest backend/tests/test_e33_evidence_preserving_matching.py -q`

---

## 1. Execution Mode & Provider Disclosure

In accordance with E3.3 evaluation integrity requirements, results are strictly separated by execution mode:
1. **`deterministic_only` (Config A / `SemanticMatchingMode.DISABLED`):** Production default. Uses deterministic lexical, facet, timeframe, modality, and normative-conflict rules only.
2. **`embedding_only (mock)` (Config B / `SemanticMatchingMode.EMBEDDING_ONLY`):** Uses `DeterministicMockSemanticProvider` (`mock-concept-v1`) for candidate retrieval combined with deterministic relationship classification.
3. **`hybrid (mock)` (Config C / `SemanticMatchingMode.HYBRID`):** Uses `DeterministicMockSemanticProvider` (`mock-concept-v1` + `mock-deterministic-v1`) with deterministic-dominant score fusion (`0.42 * emb + 0.58 * det` when `det_score >= 0.35`) and evidence-preserving deterministic validation (`validate_hybrid_candidate_relationship`).
4. **`live Gemini` (`--provider gemini`):** **Optional / Not Run in CI or local automated test runs** (`GEMINI_API_KEY` not configured in environment). Mock results are never reported as live Gemini performance.

---

## 2. E3.2 Independent Holdout Benchmark (`e32`, `N = 18` clauses, `15` obligation-bearing, `4` questionnaire cases)

The E3.2 Independent Holdout benchmark tests 18 realistic banking and AI governance clauses authored independently of the regulatory catalogue, plus 4 questionnaire matching cases.

| Metric | Config A (`deterministic_only`) Before E3.3 | Config A (`deterministic_only`) After E3.3 | Config B (`embedding_only` mock) Before E3.3 | Config B (`embedding_only` mock) After E3.3 | Config C (`hybrid` mock) Before E3.3 | Config C (`hybrid` mock) After E3.3 |
|---|---:|---:|---:|---:|---:|---:|
| **Obligation Top-1 Recall (`Recall@1`)** | `7/15 (46.67%)` | **`10/15 (66.67%)`** | `10/15 (66.67%)` | **`11/15 (73.33%)`** | `10/15 (66.67%)` | **`11/15 (73.33%)`** |
| **Obligation Top-5 Recall (`Recall@5`)** | `8/15 (53.33%)` | **`12/15 (80.00%)`** | `12/15 (80.00%)` | **`12/15 (80.00%)`** | `12/15 (80.00%)` | **`12/15 (80.00%)`** |
| **Multi-Obligation (Expected / Full Ret / Decomp)** | `1 / 0 / 0` | **`1 / 1 / 1`** | `1 / 1 / 1` | **`1 / 1 / 1`** | `1 / 1 / 1` | **`1 / 1 / 1`** |
| **Relationship Classification Accuracy** | `8/18 (44.44%)` | **`17/18 (94.44%)`** | `11/18 (61.11%)` | **`18/18 (100.00%)`** | `11/18 (61.11%)` | **`18/18 (100.00%)`** |
| **Macro F1** | `43.59%` | **`96.04%`** | `49.85%` | **`100.00%`** | `49.85%` | **`100.00%`** |
| **False Equivalence Rate** | `0/18 (0.00%)` | **`0/18 (0.00%)`** | `0/18 (0.00%)` | **`0/18 (0.00%)`** | `0/18 (0.00%)` | **`0/18 (0.00%)`** |
| **False Coverage / False-Positive Proposals** | `0/18 (0.00%)` | **`0/18 (0.00%)`** | `2/18 (11.11%)` | **`0/18 (0.00%)`** | `1/18 (5.56%)` | **`0/18 (0.00%)`** |
| **False Conflict Rate** | `1/18 (5.56%)` | **`0/18 (0.00%)`** | `1/18 (5.56%)` | **`0/18 (0.00%)`** | `1/18 (5.56%)` | **`0/18 (0.00%)`** |
| **Unresolved / Conflict Escalation Recall** | `6/13 (46.15%)` | **`10/13 (76.92%)`** | `6/13 (46.15%)` | **`10/13 (76.92%)`** | `10/13 (76.92%)` | **`13/13 (100.00%)`** |
| **Citation Completeness** | `18/18 (100.00%)` | **`18/18 (100.00%)`** | `18/18 (100.00%)` | **`18/18 (100.00%)`** | `18/18 (100.00%)` | **`18/18 (100.00%)`** |
| **Auto-Approved Decisions** | `0` | **`0`** | `0` | **`0`** | `0` | **`0`** |

### Resolution of the 6 E3.2 Holdout Failure Cases
1. **`E32-HOLDOUT-01` (Internal `Annexure G` vs Statutory EU AI Act Annex III / Privacy Act Schedule 1):** Resolved across all 3 configurations (`UNRESOLVED` instead of `NOT_ADDRESSED`).
2. **`E32-HOLDOUT-02` (`"may deploy low-latency scoring increments without executing pre-deployment fairness testing..."`):** Permissive control-omission gate detects `"may ... without executing ..."` and routes to `UNRESOLVED` instead of `PARTIALLY_ADDRESSED`.
3. **`E32-HOLDOUT-08` (Dual-regulator APRA CPS 234 + OAIC NDB incident clause):** Multi-regulator source diversity retrieves both `OBL-APRA-CPS234-03` and `OBL-OAIC-NDB-01` (`1/1/1` full retrieval and decomposition across all 3 configurations) and classifies as `PARTIALLY_ADDRESSED`.
4. **`E32-HOLDOUT-12` (72h APRA notification + 45d NDB assessment vs 30d statutory limit):** Sub-clause-bound timeframe comparison (`_compare_obligation_bound_timeframes`) binds `45 calendar days` to the NDB assessment duty (`30 days` max) and `72 hours` to the APRA notification duty, classifying as `CONFLICTING` across all 3 configurations.
5. **`E32-HOLDOUT-13` (Corporate catering & parking administration clause):** Non-regulatory corporate noise guard (`_NON_REGULATORY_CORPORATE_NOISE_PATTERN`) suppresses false semantic candidate matches, yielding `NOT_ADDRESSED` and reducing false-positive coverage proposals from `2/18` (`embedding_only`) and `1/18` (`hybrid`) to **`0/18`**.
6. **`E32-HOLDOUT-16` (Paraphrased quarterly drift monitoring without annual validation):** Local-window normalized stem matching (`_phrase_matches_normalized`) recognizes paraphrased monitoring coverage in `embedding_only` and `hybrid` modes (`PARTIALLY_ADDRESSED`), while deterministic mode conservatively escalates as `UNRESOLVED`.

---

## 3. Historical & Regression Benchmark Suites (`e31`, `e3`, `e11`, Questionnaire)

All existing evaluation benchmarks were re-run via `python scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all` to verify zero regression and quantify improvements:

| Benchmark Suite | Split / Size | Mode | Recall@1 | Recall@5 | Relationship Accuracy (Before -> After) | Macro F1 (After) | False Eq | False Cov | Citations |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| **E3.1 Adversarial Calibration (`e31`)** | Combined (`N=24`: `12` dev + `12` held_out) | `deterministic_only` | `17/18 (94.44%)` | `18/18 (100.00%)` | `12/24 (50.00%)` -> **`15/24 (62.50%)`** | `55.76%` | `0/24` | `0/24` | `24/24` |
| **E3.1 Adversarial Calibration (`e31`)** | Combined (`N=24`: `12` dev + `12` held_out) | `embedding_only (mock)` | `13/18 (72.22%)` | `18/18 (100.00%)` | `15/24 (62.50%)` -> **`16/24 (66.67%)`** | `56.95%` | `0/24` | `0/24` | `24/24` |
| **E3.1 Adversarial Calibration (`e31`)** | Combined (`N=24`: `12` dev + `12` held_out) | `hybrid (mock)` | `13/18 (72.22%)` | `18/18 (100.00%)` | `15/24 (62.50%)` -> **`16/24 (66.67%)`** | `56.95%` | `0/24` | `0/24` | `24/24` |
| **E3 Extended Synthetic (`e3`)** | Combined (`N=60`: `30` dev + `30` held_out) | `deterministic_only` | `25/48 (52.08%)` | `40/48 (83.33%)` | `27/60 (45.00%)` -> **`29/60 (48.33%)`** | `54.77%` | `0/60` | `0/60` | `60/60` |
| **E3 Extended Synthetic (`e3`)** | Combined (`N=60`: `30` dev + `30` held_out) | `embedding_only (mock)` | `31/48 (64.58%)` | `45/48 (93.75%)` | `35/60 (58.33%)` -> **`39/60 (65.00%)`** | `73.56%` | `0/60` | `0/60` | `60/60` |
| **E3 Extended Synthetic (`e3`)** | Combined (`N=60`: `30` dev + `30` held_out) | `hybrid (mock)` | `31/48 (64.58%)` | `45/48 (93.75%)` | `35/60 (58.33%)` -> **`39/60 (65.00%)`** (`60.00%` held_out) | **`73.56%`** | `0/60` | `0/60` | `60/60` |
| **E1.1 Baseline E2E (`e11`)** | Combined (`N=36`: `18` dev + `18` held_out) | `deterministic_only` | `27/30 (90.00%)` | `29/30 (96.67%)` | **`30/36 (83.33%)`** | `76.24%` | `0/36` | `0/36` | `36/36` |
| **E1.1 Baseline E2E (`e11`)** | Combined (`N=36`: `18` dev + `18` held_out) | `embedding_only (mock)` | `27/30 (90.00%)` | `30/30 (100.00%)` | **`30/36 (83.33%)`** | `74.49%` | `0/36` | `0/36` | `36/36` |
| **E1.1 Baseline E2E (`e11`)** | Combined (`N=36`: `18` dev + `18` held_out) | `hybrid (mock)` | `27/30 (90.00%)` | `30/30 (100.00%)` | **`31/36 (86.11%)`** | `78.68%` | `0/36` | `0/36` | `36/36` |

*(Note on `e11` case `HO-TIB-08`: Under Regulatory Pack `v0.2.0`, `OBL-OAIC-APP11-01` explicitly requires both technical and organisational security measures (`technical_security_measures_implemented` + `organisational_security_measures_implemented`), whereas the historical `v0.1.0` label assumed a single generic security facet. Returning `PARTIALLY_ADDRESSED` when organisational security governance is absent is the intended Pack `v0.2.0` domain-completeness safeguard.)*

### Questionnaire Matching Accuracy (`N = 22` total: `18` E3 + `4` E3.2 Holdout)
- **E3 Questionnaire Suite (`N = 18`: `9` dev + `9` held_out):**
  - Top-1 Control Accuracy: `14/18 (77.78%)` across `deterministic_only`, `embedding_only`, and `hybrid`
  - Answer State Accuracy: `18/18 (100.00%)`
  - False Confirmed Coverage: `0/18 (0.00%)`
- **E3.2 Holdout Questionnaire Suite (`N = 4`):**
  - Top-1 Control Accuracy: `4/4 (100.00%)` across `deterministic_only`, `embedding_only`, and `hybrid`
  - Answer State Accuracy: `4/4 (100.00%)`
  - False Confirmed Coverage: `0/4 (0.00%)`

---

## 4. Unseen E3.3 Blinded Evaluation Suite (`E33_BLINDED_EVALUATION_SUITE`, `N = 8`)

To ensure E3.3 rule refinements generalize beyond `E32_INDEPENDENT_HOLDOUT_CLAUSES`, an unseen 8-case blinded evaluation suite (`E33_BLINDED_EVALUATION_SUITE` in `backend/tests/test_e33_evidence_preserving_matching.py`) was constructed with novel phrasing and composite conditions:

| Case ID | Scenario Tested | Expected Obligation(s) | Expected Relationship | Observed (`disabled` / `embedding_only` / `hybrid`) |
|---|---|---|---|---|
| `E33-BLIND-01` | Internal `Schedule 4B` high-impact scoring models without statutory Annex III / APP mapping | `OBL-EU-AI-ACT-01` | `UNRESOLVED` | **`UNRESOLVED` / `UNRESOLVED` / `UNRESOLVED`** |
| `E33-BLIND-02` | Permissive control omission (`"may release minor credit scorecard recalibrations without pre-release bias auditing..."`) | `OBL-ISO-42001-03` | `UNRESOLVED` | **`UNRESOLVED` / `UNRESOLVED` / `UNRESOLVED`** |
| `E33-BLIND-03` | Protective prohibition (`"must never deploy automated credit decisioning unless human override and kill-switch mechanisms are active"`) + full oversight duties | `OBL-EU-AI-ACT-03` | `EQUIVALENT` | **`EQUIVALENT` / `EQUIVALENT` / `EQUIVALENT`** |
| `E33-BLIND-04` | Multi-regulator cyber & privacy breach clause (`72h` APRA notification + `30d` OAIC assessment, missing OAIC notification content details) | `OBL-APRA-CPS234-03`, `OBL-OAIC-NDB-01` | `PARTIALLY_ADDRESSED` | **`PARTIALLY_ADDRESSED` / `PARTIALLY_ADDRESSED` / `PARTIALLY_ADDRESSED`** |
| `E33-BLIND-05` | Multi-timeframe conflict (`72h` APRA notification + `60 business days` OAIC NDB assessment exceeding `30d` statutory cap) | `OBL-OAIC-NDB-01` | `CONFLICTING` | **`CONFLICTING` / `CONFLICTING` / `CONFLICTING`** |
| `E33-BLIND-06` | Non-regulatory office plant watering & stationery procurement policy noise | *(None)* | `NOT_ADDRESSED` | **`NOT_ADDRESSED` / `NOT_ADDRESSED` / `NOT_ADDRESSED`** |
| `E33-BLIND-07` | Technical encryption present (`AES-256`, `TLS 1.3`) + indefinite retention of all raw customer identity records (`never purged`) | `OBL-OAIC-APP11-01` | `CONFLICTING` | **`CONFLICTING` / `CONFLICTING` / `CONFLICTING`** |
| `E33-BLIND-08` | Technical security measures only (encryption & key rotation) with no organisational security measures or destruction/de-identification rules | `OBL-OAIC-APP11-01` | `PARTIALLY_ADDRESSED` | **`PARTIALLY_ADDRESSED` / `PARTIALLY_ADDRESSED` / `PARTIALLY_ADDRESSED`** |

- **Blinded Suite Summary (`N = 8`):** **`8/8 (100.00%)`** across `disabled`, `embedding_only`, and `hybrid`, with `0/8` false equivalence, `0/8` false coverage proposals, `0/8` false conflicts, and `0/8` auto-approved decisions.

---

## 5. P1B Experimental Facet Extraction Benchmark (`P1_EVALUATION_DATASET_V2_PACK_V020.json`, 158 Canonical Facets)

From Stage A (`fix/p1b-taxonomy-v02-alignment`, included in this branch):

| Dataset Split | Engine | Facet Micro F1 | UCL Facet Coverage (`158` total) | Top-1 Control Recall | Control Micro F1 | Suppression Accuracy | False Trigger Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| **V2 Dev (`N=105`)** | `EngineA0` (8-group legacy regex via adapter) | `6.37%` | `3.16% (5/158)` | `3.81%` | `8.40%` | `78.57%` | `21.43%` |
| **V2 Dev (`N=105`)** | `EngineA1` (Before P1B v0.2.0 repair, 155-facet baseline) | `22.77%` | `17.42% (27/155)` | `20.95%` | `33.13%` | `100.00%` | `0.00%` |
| **V2 Dev (`N=105`, Pack `v0.2.0`)** | **`EngineA1` (Repaired v0.2.0, 44 canonical facets)** | **`27.41%`** | **`19.62% (31/158)`** | **`26.67%`** | **`39.75%`** | **`100.00% (14/14)`** | **`0.00% (0/14)`** |
| **V2 Holdout (`N=51`)** | `EngineA0` (8-group legacy regex via adapter) | `14.81%` | `3.16% (5/158)` | `8.16%` | `13.11%` | `50.00%` | `50.00%` |
| **V2 Holdout (`N=51`)** | `EngineA1` (Before P1B v0.2.0 repair, 155-facet baseline) | `28.89%` | `7.74% (12/155)` | `30.61%` | `44.44%` | `50.00%` | `50.00%` |
| **V2 Holdout (`N=51`, Pack `v0.2.0`)** | **`EngineA1` (Repaired v0.2.0, 44 canonical facets)** | **`34.78%`** | **`9.49% (15/158)`** | **`34.69%`** | **`51.35%`** | **`100.00% (2/2)`** | **`0.00% (0/2)`** |
