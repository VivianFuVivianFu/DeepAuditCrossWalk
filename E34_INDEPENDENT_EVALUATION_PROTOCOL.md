# E3.4 Independent Evaluation Protocol, Dataset Epistemic Classification & Observed Un-Tuned Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Frozen Evaluation Dataset:** [`E34_INDEPENDENT_EVALUATION_DATASET.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/E34_INDEPENDENT_EVALUATION_DATASET.json) & [`backend/tests/e34_independent_evaluation_dataset.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/e34_independent_evaluation_dataset.py)  
**Immutable Dataset SHA-256:** `a3ad93a89cf5dd8b5125306d3207519e86ef3cc49d95bbc2fe6d61267a462826`  
**Regulatory Pack:** `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`46` obligations, `33` controls, `158` canonical facets, `0` human-approved mappings)

---

## 1. Epistemic Classification of All Existing Benchmarks (Phase 4)

Per Phase 4 scientific governance, datasets touched or inspired by rule development must be reclassified as **regression suites**, never presented as independent generalisation evidence:

| Dataset | Size | Epistemic Classification | Why Reclassified / Status | SHA-256 Hash |
|---|---:|---|---|---|
| `P1_EVALUATION_DATASET_V2.json` | 156 | **Historical Regression Baseline (`v1.0.0`)** | Used iteratively during P1 development against 155-facet schema | `3ee3241ce557b423584c9cda805f534001ed044178d465025d9c9e1ef3007569` |
| `P1_EVALUATION_DATASET_V2_PACK_V020.json` | 156 | **Pack `v0.2.0` Regression Suite** | Migrated from P1 V2; used to calibrate Stage A `EngineA1` | `41250ae07668685f5afeec18fb7a4993bf1ade413715d64cad4f00ecf757e8a1` |
| `P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json` | 36 | **Adversarial Prohibition Regression Suite** | Used directly to tune Stage A `EngineA1` normative suppression | `5f164cdcb69f9034386b4a2f123ddf964783ced75dc5cf091723d861aa432f68` |
| `e11_benchmark_dataset.py` (`E11`) | 36 | **Historical Regression Suite** | Original E1.1 development & holdout benchmark | `d4779820c4154550c871dd47f81d8f75a4ef2c1f9c8c8f67ef865a2d99848ab6` |
| `e3_benchmark_dataset.py` (`E3` + `Q`) | 60 + 20 | **Historical Regression Suite** | Synthetic dataset used during E3 semantic integration | `b982008b4f8c8f95440e5cd6f3bff3802601aa1eee93b6e8da3ad6f464e41bb2` |
| `e31_calibration_dataset.py` (`E31`) | 24 | **Historical Calibration Regression Suite** | Used directly during E3.1 mock & fallback calibration | `1051a63161d9c32f3f47d3906d4cf06f1ba0bb9c4b890d46e68932c11a72c88a` |
| `e32_independent_holdout.py` (`E32` + `Q`) | 18 + 4 | **Contaminated Regression Suite** | Originally uncontaminated in E3.2 (`44.44%`/`61.11%`); became **contaminated in E3.3** when all 6 failure categories were fixed (`94.44%`/`100.00%`) | `d7200a34514961c0fbac158718f1575c80d1a994a5b455c707595d63cbcbaf48` |
| `E33_BLINDED_EVALUATION_SUITE` | 8 | **E3.3 Synthetic Regression Suite** | **Explicitly downgraded from "blinded"**: authored in the same PR as E3.3 rules to verify the 6 failure patterns | Embedded in `test_e33_evidence_preserving_matching.py` |
| **`E34_INDEPENDENT_EVALUATION_DATASET` (`e34`)** | **30 + 8** | **Frozen Un-Tuned Evaluation Dataset (Phase 4)** | Prepared after freezing matching rules; realistic AU banking phrasing across 5 multi-clause docs (PDF/DOCX/TXT); **zero post-evaluation rule tuning** | **`a3ad93a89cf5dd8b5125306d3207519e86ef3cc49d95bbc2fe6d61267a462826`** |

---

## 2. Dataset Composition & Sample Size Limits

`E34_INDEPENDENT_EVALUATION_DATASET` contains `30` policy clauses (`25` obligation-bearing, `5` unmapped/internal/ambiguous, `2` multi-obligation compound clauses, `22` requiring human resolution) across 5 realistic synthetic banking documents (`PDF`, `DOCX`, `TXT`), plus `8` holdout institutional questionnaire cases:
- **Positive Equivalents (`5`):** `APP 1` governance, `APP 8` cross-border, `CPS 234` incident, `RG 271` complaint handling, `NAIC AI6` human oversight.
- **Partial Coverage (`9`):** OAIC PIA, `APP 11.3` technical-only, `APP 1.7` missing decision kinds, `CPS 230` SP missing exit, `CPS 230` BCP missing continuity tests, `RG 271` systemic missing remediation, `NCCP s 128` missing written record, `EU AI Act Art 26/27` missing 6m logs, `NIST MEASURE/MANAGE` missing TEVV.
- **Stricter Enterprise (`2`):** `12h` APRA notification, `AUD 250` dual-approval protective prohibition.
- **Waivers / Exceptions / Weaker Timing or Currency (`4`):** `USD 10,000` mismatch, post-execution Team Leader review, `APP 3` consent waiver above AUD 50k.
- **Active Contradictions (`4`):** `APP 11` indefinite retention (*"must not be destroyed"*), `15-day` CPS 234 deadline, `RG 271` permissive omission, `ASIC REP 798` *"not required"*.
- **Ambiguous (`2`):** management discretion & missing `Annexure D2`.
- **Multi-Obligation (`2`):** `CPS 234` 72h + `OAIC NDB` 30d; `CPS 230` offshoring + `APP 8` cross-border.
- **Non-Obligation Controls / Distractors (`3` total including internal):** `7-year` WORM prompt telemetry (internal enterprise-only), brand typography slides, Scope 2 ESG liquid cooling.

**Statistical Uncertainty Disclosure:** At `N = 30` clauses (`N = 25` retrieval queries), binomial Wilson 95% confidence intervals remain approximately `±15–18` percentage points wide. Authored by the engineering team (though frozen prior to execution without post-hoc tuning); independent external compliance-practitioner annotation and live Gemini execution on this exact frozen dataset remain necessary before statistical release claims.

---

## 3. Observed Un-Tuned Evaluation Results (`e34`, Frozen Rules)

Reproduced via `python scripts/evaluate_e3_live_gemini.py --provider mock --benchmark e34 --split all` and [`test_e34_phase4_frozen_independent_dataset_integrity_and_evaluation`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e34_integration_and_facet_validation.py).

| Metric | Config A (`deterministic_only`) | Config B (`embedding_only`, mock) | Config C (`hybrid`, mock) |
|---|---:|---:|---:|
| **Candidate Recall@1 (95% Wilson CI)** | `21/25 (84.00%, [65.35%, 93.60%])` | `22/25 (88.00%, [70.04%, 95.83%])` | `22/25 (88.00%, [70.04%, 95.83%])` |
| **Candidate Recall@5 (95% Wilson CI)** | `25/25 (100.00%, [86.68%, 100.00%])` | `25/25 (100.00%, [86.68%, 100.00%])` | `25/25 (100.00%, [86.68%, 100.00%])` |
| **Multi-Obligation (Ret / Dec / Tot)** | `2 / 2 / 2` | `2 / 2 / 2` | `2 / 2 / 2` |
| **Relationship Accuracy (95% Wilson CI)** | **`17/30 (56.67%, [39.20%, 72.62%])`** | **`17/30 (56.67%, [39.20%, 72.62%])`** | **`18/30 (60.00%, [42.32%, 75.41%])`** |
| **Relationship Macro F1** | `59.01%` | `58.89%` | **`71.76%`** |
| **Canonical Facet Precision (Micro)** | `30/47 (63.83%)` | `47/68 (69.12%)` | `45/67 (67.16%)` |
| **Canonical Facet Recall (Micro)** | `30/60 (50.00%)` | `47/60 (78.33%)` | `45/60 (75.00%)` |
| **Canonical Facet F1 (Micro)** | `56.07%` | **`73.44%`** | `70.87%` |
| **False-Positive Coverage Proposals** | `1/5` | `1/5` | **`0/5`** |
| **False-Negative Obligation Omissions** | `2/25` | **`0/25`** | **`0/25`** |
| **False Equivalence** | `1/30` (`E34-IND-02`) | `2/30` (`E34-IND-02`, `-24`) | `2/30` (`E34-IND-02`, `-24`) |
| **False Conflict** | `0/30` | `0/30` | `0/30` |
| **Incorrect Deterministic Vetoes** | `0` (`valid=0`) | `0` (`valid=0`) | `3` (`valid=2`) |
| **Missing Evidence Detection Rate** | `6/18 (33.33%)` | `6/18 (33.33%)` | `6/18 (33.33%)` |
| **Unresolved-Condition Recall** | `16/22 (72.73%)` | `15/22 (68.18%)` | **`20/22 (90.91%)`** |
| **Correct Source Attribution** | `18/25 (72.00%)` | `20/25 (80.00%)` | `20/25 (80.00%)` |
| **Questionnaire Recall@1 / Recall@3** | `8/8` / `8/8` (`0` confirmed) | `8/8` / `8/8` (`0` confirmed) | `8/8` / `8/8` (`0` confirmed) |

---

## 4. Genuine Un-Tuned Failure Analysis (Why Independent Score Is `56.67%–60.00%`, Not `100%`)

Inspecting the un-tuned misses on `E34_INDEPENDENT_EVALUATION_DATASET` proves why independent testing matters far more than regression scores:

1. **Indicative Policy Phrasing Sets `mandatory=False` (`8` misses across all 3 modes: `E34-IND-01, 06, 08, 14, 15, 17, 18, 23`):**
   - Realistic Australian banking policies frequently state mandatory controls in present indicative declarative prose (e.g., *"the bank assigns executive privacy accountability... implements documented privacy practices... maintains incident detection mechanisms... complaints are broadly recognised"* rather than repeating *"must"* / *"shall"*).
   - `policy.py` (`MANDATORY_PATTERN`) only matches explicit modal verbs (`must`, `shall`, `required to`), setting `clause.mandatory = False` and triggering `modality_comparison = "enterprise_discretionary_vs_mandatory"` $\rightarrow$ **`weaker_or_potentially_insufficient`** even when every facet matches (causing `3` incorrect deterministic vetoes when hybrid mock correctly identified candidate equivalence on declarative clauses `E34-IND-01`, `-08`, `-15`? Wait — in `E34-IND-01` mock also got modality mismatch from `_dimension_precheck_summary`).
2. **Sub-Clause Optionality Ignored When Keyword Appears (`2` false equivalences: `E34-IND-02`, `E34-IND-24`):**
   - `E34-IND-02`: *"...embed privacy-by-design controls, though tracking PIA recommendations to formal closure remains optional."*
   - Because `_infer_canonical_obligation_facets_for_clause()` matches `"PIA recommendations"` positively and `"remains optional"` is outside `CONDITIONAL_PATTERN` / `EXCEPTION_PATTERN`, all 3 facets appeared satisfied, yielding `EQUIVALENT` (False Equivalence). Same pattern occurred on `E34-IND-24` (*"...while formal TEVV validity and reliability benchmarking is not yet standardised"*) in `embedding_only` and `hybrid`.
3. **Prohibited Deletion Without `"does not require"` Wording (`E34-IND-05`):**
   - *"personal information... must be retained indefinitely and must not be destroyed or de-identified"* uses negative protective grammar (*"must not be destroyed"*) to defeat a positive deletion duty (`APP 11.2`), whereas `ABSENCE_OF_CONTROL_PATTERN` looks primarily for waiver verbs (`does not require`, `need not`), classifying `E34-IND-05` as `partially_overlapping` instead of `potential_conflict`.
4. **Strict Pre-Execution Timing Classified as Stricter (`E34-IND-21`):**
   - Adding explicit `AUD 1,000` + pre-execution gate to `AU-NAIC-AI6-TEST-HUMAN` triggered `stricter_enterprise_requirement` instead of `equivalent` (arguably more accurate conservatively, as NAIC AI6 does not specify a dollar threshold).

**Decision:** Per Phase 4 rules, we did **not** post-hoc tune rules on `E34_INDEPENDENT_EVALUATION_DATASET`. Instead, these 3 genuine findings define the concrete technical backlog required before promoting deterministic accuracy beyond conditional internal pilot use.
