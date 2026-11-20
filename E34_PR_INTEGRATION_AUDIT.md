# E3.4 PR Dependency, Integration Audit & Production Wiring Verification

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Audit Date:** 2026-11-20  
**Regulatory Pack Baseline:** `AU-BANKING-REG-PACK-0.1` v`0.2.0` (`17` sources, `46` atomic obligations, `33` unified controls, `158` canonical facets, `55` active mappings v`1.1.0`, `0` human-approved mappings)  
**Target Integration Sequence:** `PR #39` $\rightarrow$ `PR #40` $\rightarrow$ `PR #41` $\rightarrow$ `E3.4 PR` (`fix/e34-integration-evaluation-assurance`)

---

## 1. Phase 1 — Branch Ancestry, Shared Commits & Overlap Audit

### 1.1 Exact Branch Heads & Ancestry
| Branch / PR | Head Commit SHA | Relation to `main` (`e47f66d0`) | Diff Size vs `main` |
|---|---|---|---|
| `main` (`PR #38` E4.1) | `e47f66d0bf9a75c0d305502ec1c4f8bd04e79db6` | Base | — |
| **PR #39** (`feat/e32-live-gemini-accuracy-validation`) | `1f4a367beace26a04ac75f64d618de7ad3f208b6` | `2` commits ahead (`e43dfcc`, `1f4a367`) | `12` files (`+20,413 / -8`) |
| **PR #40** (`fix/p1b-taxonomy-v02-alignment`) | `fa3a7bee04ccb1b2dae8e740da9a85cbff4a6fc5` | `2` commits ahead (`f752e7c`, `fa3a7be`) | `46` files (`+35,738 / -1,254`) |
| **PR #41** (`fix/e33-evidence-preserving-matching`) | `e74aeaf65207bf58fbf487abb59d92cdc1fe0a96` | Merges PR #39 (`1f4a367`) into PR #40 (`fa3a7be`) at `16a04b3`, then Stage B `e74aeaf` | `71` files (`+57,888 / -1,346`) |
| **E3.4 Branch** (`fix/e34-integration-evaluation-assurance`) | Branched from `e74aeaf` | Regression fixes, frozen E3.4 independent evaluation, 158-facet matrix audit & E3.4 reports | Diff narrows cleanly once #39/#40/#41 merge |

### 1.2 Shared Commits & File-Level Overlap Analysis
- **Merge bases:**
  - `git merge-base PR#39 PR#41` = `1f4a367beace26a04ac75f64d618de7ad3f208b6`
  - `git merge-base PR#40 PR#41` = `fa3a7bee04ccb1b2dae8e740da9a85cbff4a6fc5`
- **Overlapping files between PR #39 and PR #40 (2 files only):**
  1. [`scripts/check_web_npm_audit.mjs`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/check_web_npm_audit.mjs) — **Byte-for-byte identical** across commit `1f4a367` (PR #39) and commit `fa3a7be` (PR #40). Zero conflict.
  2. [`.github/workflows/ci.yml`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/.github/workflows/ci.yml) — Both PR #39 (`1f4a367`) and PR #40 (`fa3a7be`) made the identical 1-line addition `node ../scripts/check_web_npm_audit.mjs` in the `web` job; PR #40 additionally updated lines 23–25 of the `backend` job to run `ruff check backend scripts/experiments` and `PYTHONPATH=. python -m pytest scripts/experiments -q`. Zero conflict (`git diff PR#39 PR#40 -- .github/workflows/ci.yml` confirms disjoint hunks).
- **Overlap between PR #39 / PR #40 and unique Stage B changes in PR #41 (`16a04b3..e74aeaf`):**
  - **0 overlapping files** (`15` unique files added/modified cleanly in `16a04b3..e74aeaf`).

### 1.3 Simulated Sequential Merge Verification (`git merge-tree --write-tree`)
Simulated sequentially against `main` (`e47f66d0`):
1. `main + PR #39`: Tree `b8b0218eec5d854bdea6af8f6c83d770e94841db` — **exit 0, 0 conflicts**.
2. `(main + PR #39) + PR #40`: Tree `82508db56a68b994c12a409f648cd7f8b54abd08` — **exit 0, 0 conflicts**.
3. `((main + PR #39) + PR #40) + PR #41`: Tree `4494197b28659b24f3f4804c56cd723e506a59f5` — **exit 0, 0 conflicts**.

### 1.4 PR #41 Diff Narrowing After Merging Dependencies
Because PR #41 currently appears against `main` as `71` files (`+57,888 / -1,346`), merging `PR #39` $\rightarrow$ `PR #40` first narrows PR #41's diff (`git diff <m2> <m3> --stat`) strictly to its **15 scoped Stage B E3.3 files (`+1,894 / -85`)**:
- Core backend: `models.py`, `policy.py`, `coverage.py`, `reconciliation.py`, `semantic_reconciliation.py`, `llm/providers.py`
- Verification & script: `backend/tests/test_e33_evidence_preserving_matching.py`, `scripts/generate_e33_facet_matrix.py`
- Documentation & CSV: `E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv` and the 6 `E33_*.md` reports.

### 1.5 Integration Protocol (No Auto-Merge)
1. **Merge order:** Maintainer reviews and merges **PR #39** $\rightarrow$ **PR #40** $\rightarrow$ **PR #41** $\rightarrow$ **E3.4 PR (`fix/e34-integration-evaluation-assurance`)**.
2. **Synchronization after merge commits:** If GitHub creates merge or squash commits on `main`, update the next open PR branch against `origin/main` (`git merge origin/main`), confirm zero duplicate/stale hunks in `.github/workflows/ci.yml`, and await green CI before merging the next PR in sequence.
3. **Existing PRs Preserved Intact:** PR #39 (`1f4a367`), PR #40 (`fa3a7be`), and PR #41 (`e74aeaf`) are preserved with their original scoped commits and green GitHub CI/CodeQL runs. E3.4 integration/regression fixes, frozen independent evaluation, and facet matrix corrections are isolated in `fix/e34-integration-evaluation-assurance`.

---

## 2. Phase 2 — Verification of Production Execution Wiring & Backward Compatibility

We verified that E3.3 enhancements and E3.4 regression fixes execute in the **live FastAPI production request path** ([`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)), not merely in standalone helper scripts:

| Subsystem | Verification Audit Result | Production Entry Point / Evidence |
|---|---|---|
| **Taxonomy (Stage A / Pack `v0.2.0`)** | Dynamic `158`-facet loading (`UNIFIED_CONTROL_LIBRARY.json`), retired `security_controls_defined` & `deployer_human_oversight_and_6month_log_retention` decomposition, evidence-gated `migrate_legacy_facet()` protecting un-evidenced sibling facets | `scripts/experiments/canonical_adapter.py`, `scripts/experiments/engine_a1.py`, [`backend/banking_crosswalk/catalog.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) (`test_regulatory_library.py` + `test_canonical_adapter.py`) |
| **Extraction (`policy.py`)** | Legacy control alias resolution (`CONTROL_ID_ALIASES` + `AMBIGUOUS_LEGACY_CONTROL_IDS`), default `MappingRelationship.PARTIAL` (never `FULL` on single keyword match), `RELATED` on ambiguous legacy controls, `PROTECTIVE_STAFF_PROHIBITION_CUES`, negation & exemption detection | [`POST /v1/enterprise/policies/import`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L1457-L1479) and `import-file` ([lines 1481–1514](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L1481-L1514)) call `extract_enterprise_policy()` |
| **Reconciliation (`reconciliation.py`, `semantic_reconciliation.py`)** | Multi-regulator source diversity, sub-clause-bound timing attribution (`_compare_obligation_bound_timeframes`), statutory Annex vs internal Annexure filter, `_NON_REGULATORY_CORPORATE_NOISE_PATTERN` rejection, evidence-preserving `ReconciliationDecision` vetoes | [`POST /v1/enterprise/baselines/{baseline_id}/reconcile`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L1762-L1884) defaults to `generate_reconciliation_candidates()` (`deterministic_only`), routing to `generate_hybrid_reconciliation_candidates()` only when `SEMANTIC_MATCHING_ENABLED=true` |
| **Experimental Isolation (`EngineA1`)** | Confirmed `scripts/experiments/` is **never imported** by production `backend/banking_crosswalk/`. `EngineA1` rules remain experimental only (honestly separated in Phase 5 matrix audit) | Verified via repo-wide import scan and Phase 5 matrix audit |
| **Backward Compatibility & Persisted Records** | Pre-E3.3 serialized `ClauseControlMapping` records without explicit `relationship` safely default to `MappingRelationship.PARTIAL`; pre-E3.3 `ReconciliationDecision` records missing `ai_proposed_relationship`, `deterministic_veto_*`, `missing_conditions_or_evidence`, `candidate_relevance_state`, or `preserved_candidate_evidence` deserialize cleanly with backward-compatible defaults | Verified in [`test_e34_phase2_production_wiring_and_backward_compatibility`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e34_integration_and_facet_validation.py) |
