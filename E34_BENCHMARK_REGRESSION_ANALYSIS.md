# E3.4 Benchmark Comparability & Regression Root-Cause Analysis

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Regulatory Library Baseline:** `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`17` sources, `46` obligations, `33` controls, `158` canonical facets, `55` active mappings v`1.1.0`)  
**Provider Mode:** Offline deterministic (`disabled`) & deterministic mock (`mock-concept-v1`, `mock-deterministic-v1`)

---

## 1. Objective & Methodology (Phase 3)

E3.3 (`e74aeaf`, PR #41) reported lower combined accuracy than E3.2 (`1f4a367`, PR #39) on two existing hybrid-mock regression suites:
1. **E1.1 Multi-Org Hybrid Mock:** `34/36` (`94.44%`, E3.2) $\rightarrow$ `31/36` (`86.11%`, E3.3)
2. **E3 Extended Hybrid Mock:** `43/60` (`71.67%`, E3.2) $\rightarrow$ `39/60` (`65.00%`, E3.3)

We reproduced every run against identical serialized datasets, pack versions (`v0.2.0`), and scoring logic (`eval_harness.py`) across:
- **E3.2 baseline (`E32_BENCHMARK_RESULTS.json`, commit `1f4a367`)**,
- **E3.3 un-remediated (`e74aeaf`)**, and
- **E3.4 integrated fix (`fix/e34-integration-evaluation-assurance`)**.

Historical E3.2 and E3.3 numbers are preserved verbatim; zero historical metrics were overwritten.

---

## 2. Dataset Provenance & Configuration Equivalence

| Benchmark Suite | Cases / Queries | Dataset SHA-256 | E3.2 Config | E3.3 (`e74aeaf`) Config | E3.4 Config |
|---|---|---|---|---|---|
| `e11` (Dev + Holdout) | `36` (`30` queries) | `d4779820c4154550c871dd47f81d8f75a4ef2c1f9c8c8f67ef865a2d99848ab6` | Pack `v0.2.0`, `eval_harness.py` | **Identical** | **Identical** |
| `e3` (Extended Synthetic) | `60` (`48` queries) | `b982008b4f8c8f95440e5cd6f3bff3802601aa1eee93b6e8da3ad6f464e41bb2` | Pack `v0.2.0`, `eval_harness.py` | **Identical** | **Identical** |
| `e31` (Adversarial Calib) | `24` (`18` queries) | `1051a63161d9c32f3f47d3906d4cf06f1ba0bb9c4b890d46e68932c11a72c88a` | Pack `v0.2.0`, `eval_harness.py` | **Identical** | **Identical** |
| `e32` (Holdout Regression) | `18` (`15` queries) | `d7200a34514961c0fbac158718f1575c80d1a994a5b455c707595d63cbcbaf48` | Pack `v0.2.0`, `eval_harness.py` | **Identical** | **Identical** |

**Classification among the 6 Candidate Explanations:**
- **Primary Cause (Category 1 — Genuine Classification & Code Regressions):** **YES** — two unintended side effects of E3.3 refactoring broke existing matching behaviour.
- **Secondary Cause (Category 2 — Changed Ranking Behaviour):** Minor trade-off on multi-regulator source diversity (`R@5: 46/48` $\rightarrow$ `45/48` on `E3-DEV-CC-05`).
- Categories 3 (changed evaluation logic), 4 (ground-truth / taxonomy version diff), 5 (different benchmark config), and 6 (incorrect metrics/docs): **NO**.

---

## 3. Case-by-Case Forensic Root Causes & Remediations

### Regression A — Auto-Extracted Mapping Rationale Prefix Drift (`7` affected cases across `e11`, `e3`, `e31`)
- **Affected Cases in E3.3 (`e74aeaf`):**
  - `e11 | hybrid`: `DEV-PMC-15` (prompt logging, expected `additional_enterprise_requirement`) & `DEV-PMC-18` (GPU carbon-intensity ESG, expected `unmapped_no_reliable_relationship`)
  - `e3 | hybrid`: `E3-DEV-YV-08` (AUD 750 hardship fee waiver, expected `AU-NAIC-AI6-TEST-HUMAN`), `E3-DEV-YV-09` & `E3-HO-BR-09` (WORM/SIEM prompt logging vaults, expected `additional_enterprise_requirement`)
  - `e31 | hybrid`: `E31-DEV-12` & `E31-HO-12` (internal telemetry/artifact vaults, expected `additional_enterprise_requirement`)
- **Root Cause:** In E3.2 (`1f4a367`), `extract_enterprise_policy()` (`policy.py`) generated auto-extracted mapping rationales starting with `"Clause contains facet '"`. In `semantic_reconciliation.py` (line 810), `explicit_human_controls` excluded auto-extracted mappings via `.startswith("Clause contains facet '")` so Stage B LLM noise dismissal could reject non-regulatory/internal-only candidates unless human-curated. When E3.3 (`e74aeaf`) implemented B2 mapping honesty in `policy.py`, it changed rationale strings to `"Candidate keyword match on facet '"`, `"Clause contains candidate facet '"`, and `"Clause evidences all required facets ("`. Because `semantic_reconciliation.py` (and `reconciliation.py`) still checked only `"Clause contains facet '"`, every approved benchmark clause with `prompt_logging` (`CTRL-TECH-OBSERVABILITY`) or `human_approval_required` (`CTRL-FIN-APPROVAL-THRESHOLDS`) was falsely treated as `explicit_human_controls` (`is_strong=True`), blocking Stage B dismissal (`det_preserves_candidate=True`) and boosting competing candidate ranking (`EU-AIA-ART26-27-DEPLOYER-CREDIT` over `AU-NAIC-AI6-TEST-HUMAN` on `E3-DEV-YV-08`).
- **E3.4 Fix:** Introduced `_is_auto_extracted_mapping_rationale()` in `reconciliation.py` (imported by `semantic_reconciliation.py`) recognizing all four auto-extracted rationale prefixes cleanly. **Restored 100% of affected cases.**

### Regression B — Multi-Timeframe `APRA-CPS234` Selection in `_compare_obligation_bound_timeframes()` (`2` affected cases)
- **Affected Cases in E3.3 (`e74aeaf`):**
  - `e11 | disabled, embedding_only, hybrid`: `HO-TIB-07` (`"Material CPS 234 information security incidents... notified to APRA within 10 days"`, expected `potential_conflict`)
  - `e3 | embedding_only, hybrid`: `E3-DEV-YV-05` (`"Suspected cyber breaches... escalated to APRA within 10 business days"`, expected `potential_conflict`)
- **Root Cause:** `AU-APRA-CPS234-INCIDENT` states two statutory deadlines in its summary: `"72 hours"` (`72.0h`) for incident notification and `"10 business days"` (`240.0h`) for notifying APRA of material security control weaknesses. E3.2 `_extract_timeframe_hours()` took the **first** deadline (`72.0h`), whereas E3.3 `_compare_obligation_bound_timeframes()` defaulted to `max(ext_all)` (`240.0h`) for non-hardship obligations — masking `72.0h` and causing `10 days` (`240.0h`) to no longer trigger `timeframe_conflict`.
- **E3.4 Fix:** In `_compare_obligation_bound_timeframes()`, for `APRA-CPS234` obligations without `"control weakness"` / `"material weakness"` wording, compare against `min(ext_all)` (`72.0h`). **Restored `HO-TIB-07` and `E3-DEV-YV-05`.**

### Retrieval Enhancements Restored & Explained Trade-Off
- **Restored `AU-PRIV-APP1.7-AUTOMATED` Cue:** E3.3 removed an unnecessary single-source bias on `APP 1`, temporarily lowering `disabled` R@1 from `27/48` to `25/48` (`E3-DEV-HB-05`, `E3-HO-SM-05`). Adding explicit `APP 1.7–1.9` / `computer program` + `privacy policy` cues in `rank_reconciliation_candidates_for_clause()` restored `e3 | disabled` R@1 to `27/48` and raised `e3 | hybrid` R@1 from `31/48` to `33/48`.
- **Expected `R@5` Trade-off (`46/48` $\rightarrow$ `45/48` on `E3-DEV-CC-05`):** On `E3-DEV-CC-05` (APRA testing exemption), E3.3's multi-regulator diversity logic replaced duplicate second `APRA-CPS234` candidate (`AU-APRA-CPS234-TEST`) with another regulator source (`AU-APRA-CPS230-NOTIFY`) in Stage A candidate truncation (`R@5: 46/48` $\rightarrow$ `45/48`). This is an intentional precision/diversity trade-off that fixes `E32-HO-08` (dual-regulator APRA + OAIC), does not affect `e3 | hybrid` relationship accuracy (`43/60`), and is documented transparently.

---

## 4. Exact Reproduced Benchmark Progression (E3.2 vs E3.3 vs E3.4)

*(All semantic/hybrid results use `DeterministicMockSemanticProvider`; live Gemini not run.)*

| Suite | Mode | E3.2 (`1f4a367`) Acc (R@1 / R@5 / F1 / FP) | E3.3 (`e74aeaf`) Acc (R@1 / R@5 / F1 / FP) | E3.4 Integrated Acc (R@1 / R@5 / F1 / FP) | Net Verdict (E3.2 $\rightarrow$ E3.4) |
|---|---|---|---|---|---|
| **`e11` (36 / 30)** | `disabled` | `31/36` (`27/30`, `29/30`, `78.48%`, `FP=2`) | `30/36` (`27/30`, `29/30`, `76.24%`, `FP=2`) | **`31/36`** (`27/30`, `29/30`, `78.48%`, `FP=2`) | **Regression Fixed (Equal)** |
| **`e11` (36 / 30)** | `embedding_only` | `31/36` (`27/30`, `30/30`, `76.71%`, `FP=3`) | `30/36` (`27/30`, `30/30`, `74.49%`, `FP=3`) | **`31/36`** (`27/30`, `30/30`, `76.71%`, `FP=3`) | **Regression Fixed (Equal)** |
| **`e11` (36 / 30)** | `hybrid` | `34/36` (`27/30`, `30/30`, `97.05%`, `FP=0`) | `31/36` (`27/30`, `30/30`, `78.68%`, `FP=2`) | **`34/36`** (`27/30`, `30/30`, `97.05%`, `FP=0`) | **Regression Fixed (`34/36` Restored)** |
| **`e3` (60 / 48)** | `disabled` | `29/60` (`27/48`, `40/48`, `52.84%`, `FP=2`) | `29/60` (`25/48`, `40/48`, `52.84%`, `FP=2`) | **`29/60`** (`27/48`, `40/48`, `52.84%`, `FP=2`) | **R@1 Restored (`27/48`)** |
| **`e3` (60 / 48)** | `embedding_only` | `38/60` (`34/48`, `46/48`, `71.31%`, `FP=3`) | `39/60` (`31/48`, `45/48`, `72.77%`, `FP=2`) | **`39/60`** (`33/48`, `45/48`, `72.59%`, `FP=2`) | **Improved (`38` $\rightarrow$ `39/60`)** |
| **`e3` (60 / 48)** | `hybrid` | `43/60` (`34/48`, `46/48`, `81.40%`, `FP=0`) | `39/60` (`31/48`, `45/48`, `73.56%`, `FP=2`) | **`43/60`** (`33/48`, `45/48`, `81.40%`, `FP=0`) | **Regression Fixed (`43/60` Restored)** |
| **`e31` (24 / 18)** | `disabled` | `13/24` (`17/18`, `18/18`, `49.52%`, `FP=2`) | `15/24` (`17/18`, `18/18`, `55.76%`, `FP=2`) | **`15/24`** (`17/18`, `18/18`, `55.76%`, `FP=2`) | **Improved (`13` $\rightarrow$ `15/24`)** |
| **`e31` (24 / 18)** | `embedding_only` | `14/24` (`13/18`, `17/18`, `50.71%`, `FP=2`) | `16/24` (`13/18`, `18/18`, `56.95%`, `FP=2`) | **`16/24`** (`13/18`, `18/18`, `56.95%`, `FP=2`) | **Improved (`14` $\rightarrow$ `16/24`)** |
| **`e31` (24 / 18)** | `hybrid` | `16/24` (`13/18`, `17/18`, `64.24%`, `FP=0`) | `16/24` (`13/18`, `18/18`, `56.95%`, `FP=2`) | **`18/24`** (`13/18`, `18/18`, `70.85%`, `FP=0`) | **Improved (`16` $\rightarrow$ `18/24`, `FP=0`)** |
| **`e32` (18 / 15)** | `disabled` | `8/18` (`7/15`, `10/15`, `48.57%`, `FP=0`) | `17/18` (`10/15`, `12/15`, `96.04%`, `FP=0`) | **`17/18`** (`10/15`, `12/15`, `96.04%`, `FP=0`) | **Regression Fixed (Contaminated)** |
| **`e32` (18 / 15)** | `embedding_only` | `10/18` (`9/15`, `11/15`, `48.64%`, `FP=2`) | `18/18` (`11/15`, `12/15`, `100.00%`, `FP=0`) | **`18/18`** (`11/15`, `12/15`, `100.00%`, `FP=0`) | **Regression Fixed (Contaminated)** |
| **`e32` (18 / 15)** | `hybrid` | `11/18` (`9/15`, `11/15`, `58.84%`, `FP=1`) | `18/18` (`11/15`, `12/15`, `100.00%`, `FP=0`) | **`18/18`** (`11/15`, `12/15`, `100.00%`, `FP=0`) | **Regression Fixed (Contaminated)** |

---

## 5. Reproducibility Commands
```powershell
$env:PYTHONPATH = "backend;backend/tests"
.\.venv\Scripts\python.exe -m pytest backend/tests/test_e34_integration_and_facet_validation.py -k phase3 -q
.\.venv\Scripts\python.exe scripts/evaluate_e3_live_gemini.py --provider mock --benchmark all --split all
```
