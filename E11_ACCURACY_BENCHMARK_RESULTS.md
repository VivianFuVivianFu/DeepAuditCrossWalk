# DeepAudit Crosswalk — E1.1 End-to-End Accuracy Benchmark Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branch:** `fix/e11-effective-baseline-accuracy-integration`  
**Test Suite:** [backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py)  
**Benchmark Status:** **Provisional Synthetic End-to-End Evaluation** ($N = 36$: Dev $N = 18$, Held-Out $N = 18$)

> [!WARNING]
> **Honest Scope & Non-Overstatement:** All figures reported here are measured end-to-end from raw `.pdf`, `.docx`, `.txt`, and `.xlsx` uploads through `POST /v1/enterprise/policies/import-file`, `POST /v1/enterprise/baselines`, `POST /v1/enterprise/baselines/{id}/reconcile`, `POST /v1/enterprise/baselines/{id}/effective-baseline`, `POST /v1/questionnaires/import`, and `POST /v1/assessments/coverage`, **without** passing target obligation IDs or manually preassigned canonical facets. They remain **provisional synthetic benchmarks** (2 Dev orgs + 2 Held-Out orgs) and must not be cited as live production accuracy on customer corpora.

---

## 1. End-to-End Benchmark Metrics Summary

| Pipeline Metric | Development Split ($N = 18$) | Held-Out Test Split ($N = 18$) | Combined ($N = 36$) | Safety Gate / Target |
| :--- | :---: | :---: | :---: | :---: |
| **Document Extraction Accuracy** (verbatim clause recovery across PDF/DOCX/TXT) | `100.0%` (`18/18`) | `100.0%` (`18/18`) | `100.0%` (`36/36`) | `100.0%` |
| **Source & Version Citation Traceability** | `100.0%` (`18/18`) | `100.0%` (`18/18`) | `100.0%` (`36/36`) | `100.0%` |
| **Candidate Retrieval `Recall@1`** (non-null obligation queries) | `92.86%` (`13/14`) | `87.50%` (`14/16`) | `90.00%` (`27/30`) | $\ge 75.0\%$ |
| **Candidate Retrieval `Recall@5`** (non-null obligation queries) | `100.0%` (`14/14`) | `93.75%` (`15/16`) | `96.67%` (`29/30`) | $\ge 85.0\%$ |
| **End-to-End Relationship Classification Accuracy** | **`77.78%`** (`14/18`) | **`100.0%`** (`18/18`) | **`88.89%`** (`32/36`) | $\ge 75.0\%$ |
| **Macro Precision** (across relationship classes) | `75.00%` (`0.7500`) | `100.0%` (`1.0000`) | — | Baseline recorded |
| **Macro Recall** (across relationship classes) | `75.00%` (`0.7500`) | `100.0%` (`1.0000`) | — | Baseline recorded |
| **Macro F1** (across relationship classes) | `74.46%` (`0.7446`) | `100.0%` (`1.0000`) | — | Baseline recorded |
| **False Equivalence Rate** (Hard Safety Gate) | **`0.0%`** (`0/18`) | **`0.0%`** (`0/18`) | **`0.0%`** (`0/36`) | **`0.0%` (Hard Gate)** |
| **False Conflict Rate** | `0.0%` (`0/18`) | `0.0%` (`0/18`) | `0.0%` (`0/36`) | $\le 5.0\%$ |
| **False Confirmed Coverage Rate** (with unapproved Q mappings) | **`0.0%`** (`0/18`) | **`0.0%`** (`0/18`) | **`0.0%`** (`0/36`) | **`0.0%` (Hard Gate)** |
| **Unresolved / Needs-Review Surfacing Rate** | `88.89%` (`8/9`) | `100.0%` (`9/9`) | `94.44%` (`17/18`) | $\ge 85.0\%$ |

---

## 2. Contrast Between E1 (PR #31) and E1.1 Real End-to-End Telemetry

| Benchmark Aspect | E1 (`test_e1_requirement_reconciliation.py`, $N = 16$) | E1.1 (`test_e11_11`, $N = 36$) |
| :--- | :--- | :--- |
| **Input Format** | In-memory Python strings (`_make_approved_clause`) | Real `.pdf`, `.docx`, `.txt` uploads + `.xlsx` questionnaires |
| **Preassigned Canonical Facets** | Yes (exact target facets given) | **No** (raw text extracted without manually seeded facets) |
| **Preselected Target Obligation** | Yes (`obligation=ob_map[target_id]`) | **No** (full 45-obligation pack searched via Stage A) |
| **Effective Baseline Assessment Check** | Separate composition unit tests | Full HTTP `POST /v1/assessments/coverage` with 8-property binding validation |
| **Measured Relationship Accuracy** | `100.0%` (Stage B unit only) | **`77.78%` Dev / `100.0%` Held-Out (`88.89%` combined)** |
| **Safety Gates (`False Equivalence` / `False Coverage`)** | `0.0%` | **`0.0%` / `0.0%`** |

---

## 3. Authentic Failure Analysis & Real Error Cases

Running the full pipeline without ground-truth shortcuts surfaced **six genuine deterministic limitations** across retrieval, extraction heuristics, and strict facet matching:

### 3.1 Relationship Classification Misses (Development Split, `4/18`)

1. **`DEV-PMC-13` (Conservative False Negative on `equivalent`)**
   - **Clause:** *"Consumer credit AI models must complete an unsuitability assessment under NCCP s 128, verify the consumer financial situation, and inquire into consumer requirements and objectives."*
   - **Ground Truth:** `AU-NCCP-S128-131-LENDING` $\rightarrow$ `equivalent`
   - **Predicted:** `AU-NCCP-S128-131-LENDING` $\rightarrow$ `partially_overlapping`
   - **Root Cause:** Stage B inferred 3 of 4 facets cleanly but refused to infer `written_unsuitability_assessment_retrievable` because the clause did not explicitly state *"written"* or *"retrievable"*. Crucially, the engine failed safely (`partially_overlapping`, not a false `equivalent`), exposing the boundary of lexical matching on statutory shorthand (`"NCCP s 128"`).

2. **`DEV-PMC-14` (Colloquial Paraphrase / Signal 4 Confidence Cut-off)**
   - **Clause:** *"Automated credit decline letters must be eyeballed by a lending specialist before dispatch to the borrower."*
   - **Ground Truth:** `AU-NCCP-S128-131-LENDING` $\rightarrow$ `partially_overlapping` (`expects_human_resolution=True`)
   - **Predicted:** `None` $\rightarrow$ `unmapped_no_reliable_relationship`
   - **Root Cause:** Stage A diagnostic ranking placed `AU-NCCP-S128-131-LENDING` at rank `#1`, **but only with score `0.096`** and zero inferred facets (`inferred_facets=[]`), below Signal 4's safety threshold (`score >= 0.30 and (inferred_facets or topic_matched)`). Colloquial prose (*"eyeballed by a lending specialist"*) has zero deterministic keyword overlap with `"human_approval_required"` or `"unsuitability_and_substantial_hardship_screen_enforced"`.

3. **`DEV-PMC-15` (Control Alias Over-Bridging on Enterprise-Only Prompt Logging)**
   - **Clause:** *"All LLM prompts and model outputs must be recorded via prompt logging in the immutable telemetry vault for 7 years."*
   - **Ground Truth:** `None` $\rightarrow$ `additional_enterprise_requirement`
   - **Predicted:** `AU-NAIC-AI6-TEST-HUMAN` $\rightarrow$ `partially_overlapping`
   - **Root Cause:** `extract_enterprise_policy()` auto-tagged `"prompt logging"` with `CTRL-TECH-OBSERVABILITY`, whose alias mapping expanded to `CTRL-HUMAN-OVERSIGHT` / `CTRL-PRIV-SECURITY-RETENTION`, causing Stage A to link the clause to `AU-NAIC-AI6-TEST-HUMAN` instead of treating prompt vault telemetry as an additional enterprise control.

4. **`DEV-PMC-18` (Keyword Extractor False Positive on Out-of-Domain ESG Telemetry)**
   - **Clause:** *"GPU cluster workload schedulers must tag carbon-intensity megawatt telemetry prior to batch inference runs."*
   - **Ground Truth:** `None` $\rightarrow$ `unmapped_no_reliable_relationship` (`expects_human_resolution=True`)
   - **Predicted:** `AU-NAIC-AI6-TEST-HUMAN` $\rightarrow$ `partially_overlapping` (`proposed`)
   - **Root Cause:** The substring `"telemetry"` inside an ESG energy-scheduling clause triggered `CTRL-TECH-OBSERVABILITY / prompt_logging` during `extract_enterprise_policy()`, pulling an unrelated environmental operations clause into Stage A reconciliation against `AU-NAIC-AI6-TEST-HUMAN` (and also causing `unresolved_surfacing_rate` to drop from `9/9` to `8/9 = 88.89%` under the high-risk relationship check).

### 3.2 Candidate Retrieval `Recall@1` / `Recall@5` Misses (`3/30` Queries)

5. **`DEV-PMC-17` (`Recall@1` Miss, `Recall@5` Hit)**
   - **Clause:** Zero data retention for external foundation model APIs (`AU-PRIV-APP11-SECURITY`).
   - **Observed Top-5:** `AU-PRIV-APP6-USE` (`0.397`), `AU-PRIV-APP3-COLLECT` (`0.392`), `AU-APRA-CPS230-OPS` (`0.390`), `AU-PRIV-APP11-SECURITY` (`0.385`), `AU-APRA-CPS230-SP` (`0.360`).

6. **`HO-ADN-13` (`Recall@5` Miss) & `HO-ADN-14` (`Recall@1` Miss)**
   - **`HO-ADN-13`:** Production AI model inventory + quarterly bias testing (`AU-ASIC-REP798-AI-GAP`) ranked `AU-NAIC-AI6-RISK-TRANSPARENCY` (`0.600`) and `AU-NAIC-AI6-ACCOUNTABILITY-IMPACT` (`0.418`) ahead of `AU-ASIC-REP798-AI-GAP` (outside Top-5) because `"model inventory"` + `"bias testing"` had stronger facet keyword hits in `AU-NAIC-AI6-*` than `AU-ASIC-REP798-AI-GAP` (`use_case_registered_in_enterprise_ai_inventory`).
   - **`HO-ADN-14`:** RG 271 complaint triage (`AU-ASIC-RG271-COMPLAINT`) ranked `AU-ASIC-RG271-SYSTEMIC` (`0.988`) at rank `#1` ahead of `AU-ASIC-RG271-COMPLAINT` (`0.803`) because `"systemic issues"` matched `AU-ASIC-RG271-SYSTEMIC` directly.

---

## 4. Effective Baseline Binding & Safety Verification (`test_e11_01` – `test_e11_10`)

All 10 deterministic binding & integration tests pass:

- `test_e11_01`: Coverage assessments omitting `effective_baseline_id` no longer attach `eff_baselines[-1]` (`effective_baseline_id=None`, `effective_baseline_binding_mode="not_bound"`).
- `test_e11_02`: Multiple Effective Baselines under different `BankingUseCase` profiles (Domestic Refund vs Offshore Credit) reject cross-context attachment (`409`) and accept matching binding (`201`).
- `test_e11_03` – `test_e11_06`: Rejects mismatched `regulatory_pack_version`, mismatched `enterprise_baseline_id`/`version`/`revision`, caller SHA-256 mismatch (`409`), tampered SHA-256 payload (`422`), and `as_of_date` mismatch (`409`).
- `test_e11_07`: Rejects stale Effective Baselines after new reconciliation review approvals or superseded policy status (`409`).
- `test_e11_08`: Rejects `effective_baseline_id` when `assessment_mode == "regulatory_only"` (`400`).
- `test_e11_09` – `test_e11_10`: Verifies `reviewed_equivalence_group` preservation, `unresolved_reconciliation_ids`, `reconciliation_conflict_gaps` (`GapType.CONTROL_CONFLICT`, `source_type="reconciliation_conflict"`), full retention of external obligations in `results`, and **`0.0%` confirmed coverage inflation**.
