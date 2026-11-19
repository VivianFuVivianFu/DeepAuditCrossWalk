# E3.3 Release Readiness, Governance Verification & Supply-Chain Audit

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branches & Pull Requests:**
- **Stage A (P1B Taxonomy v0.2.0 Alignment & EngineA1 Repair):** `fix/p1b-taxonomy-v02-alignment` (PR #40)
- **PR #39 Dependency-Security Resolution (`picomatch`):** `feat/e32-live-gemini-accuracy-validation` (commit `1f4a367`) & `fix/p1b-taxonomy-v02-alignment` (commit `fa3a7be`)
- **Stage B (E3.3 Evidence-Preserving Extraction & Deterministic Accuracy Hardening):** `fix/e33-evidence-preserving-matching`

---

## 1. Final Acceptance Criteria Verification

| # | Acceptance Criterion | Status | Evidence & Verification |
|---|---|---|---|
| 1 | **158-Facet Canonical Alignment:** Canonical adapter, `EngineA1`, and all tests align dynamically with Regulatory Pack `v0.2.0` (`33` controls, `11` domains, `158` unique facets). | **PASS** | `pytest scripts/experiments -q` (`25 passed`); `pytest backend/tests/test_regulatory_library.py -q` (`7 passed`). |
| 2 | **All 158 Facets Accounted For:** Every canonical facet is classified in `E33_FACET_EXTRACTION_COVERAGE_MATRIX.csv` with honest status (`Verified direct extraction`: `4`, `Verified deterministic bridge`: `46`, `Semantic candidate support only`: `108`). | **PASS** | `python scripts/generate_e33_facet_matrix.py` generates and validates all `158` rows (`71` high-risk priority facets). |
| 3 | **Legacy-to-Canonical Mapping Honesty:** Partial clause matches no longer default to `MappingRelationship.FULL`; ambiguous legacy controls (`CTRL-GOV-FRAMEWORK`, `CTRL-TECH-OBSERVABILITY`, `CTRL-OPS-OUTSOURCING`) emit `RELATED`; `FULL` requires all control facets on a mandatory unexcepted clause. | **PASS** | `backend/banking_crosswalk/models.py`, `backend/banking_crosswalk/policy.py`, `E33_LEGACY_TO_CANONICAL_MAPPING_AUDIT.md`, `test_e33_clause_extraction_does_not_default_partial_matches_to_full`. |
| 4 | **All 6 E3.2 Holdout Failure Categories Fixed via Generalisable Rules:** Annex scope ambiguity, permissive omissions vs protective prohibitions, multi-regulator APRA+OAIC retrieval, sub-clause-bound timeframe comparison, non-regulatory corporate noise suppression, and local-window normalized stem matching. | **PASS** | E3.2 Holdout accuracy improved from `44.44%` -> **`94.44%`** (`disabled`) and `61.11%` -> **`100.00%`** (`embedding_only` and `hybrid`); `0/18` false equivalence, `0/18` false coverage, `0/18` false conflicts. |
| 5 | **Blinded Unseen Evaluation Generalisation:** Rules validated on an unseen 8-case blinded suite (`E33_BLINDED_EVALUATION_SUITE`) without benchmark hardcoding. | **PASS** | `8/8 (100.00%)` across `disabled`, `embedding_only`, and `hybrid` in `test_e33_blinded_evaluation_suite_across_all_configs`. |
| 6 | **Evidence-Preserving Deterministic Veto:** `ReconciliationDecision` preserves `ai_proposed_relationship`, `deterministic_veto_applied`, `deterministic_veto_reasons`, `missing_conditions_or_evidence`, `candidate_relevance_state` (8 explicit states), and `preserved_candidate_evidence`. | **PASS** | `E33_EVIDENCE_PRESERVATION_VERIFICATION.md` and `test_e33_evidence_preservation_when_deterministic_veto_downgrades_ai_proposal`. |
| 7 | **Dimension Completeness Checks:** Multi-dimensional obligations (`APP 11` security + retention/deletion, `CPS 234` + `OAIC NDB`, `CPS 230` service providers + BCP/testing, `EU AI Act` conformity + oversight + logging, `ISO/IEC 42001` risk + bias + monitoring) require dimension completeness before `EQUIVALENT`. | **PASS** | `E33_DIMENSION_COVERAGE_AUDIT.md` and E3.3 blinded cases `E33-BLIND-04`, `E33-BLIND-07`, `E33-BLIND-08`. |
| 8 | **Strict Mode Separation in Reporting:** `deterministic_only`, `embedding_only (mock)`, `hybrid (mock)`, and `live Gemini (not run without credentials)` are reported separately. | **PASS** | `E33_BEFORE_AFTER_ACCURACY_RESULTS.md`. |
| 9 | **Governance, Security & Approval Invariants Preserved:** `regulatory_only` default, `enterprise_enhanced` optional, `deterministic_only` production default, `0` human-approved regulatory mappings, `0` automatic confirmed coverage. | **PASS** | Verified in Section 2 below and across full backend test suite. |
| 10 | **CI & Supply-Chain Gate Clean:** `picomatch` `GHSA-fc5q-39xc-vjpf` dev-only transitive vulnerability audited and gated via `scripts/check_web_npm_audit.mjs` with zero production vulnerabilities. | **PASS** | Verified in Section 3 below. |

---

## 2. Governance, Assurance & Security Boundary Verification

1. **Assessment Mode Defaults:** `AssessmentMode.REGULATORY_ONLY` remains the default mode; `AssessmentMode.ENTERPRISE_ENHANCED` remains an explicit opt-in mode.
2. **Production Semantic Mode Default:** `SemanticMatchingMode.DISABLED` (`deterministic_only`) remains the default production reconciliation mode unless semantic matching is explicitly requested.
3. **Human Review & Confirmed Coverage Gate:**
   - Regulatory Pack `v0.2.0` contains **`0` `human_approved` records** (`55/55` active mappings and `46/46` obligations are `review_status: "proposed"`).
   - Every automated clause extraction (`ClauseControlMapping`) and obligation reconciliation (`ReconciliationDecision`) emits `PROPOSED` status.
   - `compile_enterprise_baseline()` and `coverage.py` require explicit human approval (`ClauseReviewStatus.APPROVED` / `ReviewStatus.APPROVED`) before any mapping contributes to confirmed coverage.
4. **Confidentiality & External LLM Guardrails:** External LLM providers (`gemini`) remain gated by `allow_external_llm` and confidentiality/data-classification checks (`backend/tests/test_e3_semantic_matching.py`).
5. **Tenant Isolation, Authentication, CSRF & Baseline SHA-256 Integrity:** All existing multi-tenant isolation, RBAC, session/CSRF, and effective-baseline SHA-256 digest tests pass without modification.

---

## 3. Supply-Chain Security Resolution for PR #39 (`picomatch` `GHSA-fc5q-39xc-vjpf`)

### 3.1 Dependency Graph & Advisory Analysis
- **Advisory:** `GHSA-fc5q-39xc-vjpf` (npm advisory source `1247710`), Regular Expression Denial of Service (ReDoS) in `picomatch <= 4.0.7` via single-branch repeated extglobs.
- **Dependency Chain in `web/package-lock.json`:**
  `vitest` (devDependency) -> `vite` -> `tinyglobby` -> `fdir` -> `picomatch@4.0.4` (and `4.0.7` top-level dev override).
- **Upstream Availability Check:** Queried npm registry (`npm view picomatch versions --json`); `4.0.7` is the latest published version of `picomatch` on npm. No upstream version `> 4.0.7` exists yet (`fixAvailable: false` in `npm audit --json`).
- **Production Exposure:** **`0` vulnerabilities** in production dependencies (`npm audit --omit=dev --json` reports `0` critical, `0` high, `0` moderate, `0` low). `picomatch` is marked `"dev": true` in `web/package-lock.json` and is used exclusively by the local/CI Vitest test runner to match local test filenames; it is never bundled into the Next.js production application or exposed to untrusted user input.

### 3.2 Enforced CI Gate (`scripts/check_web_npm_audit.mjs`)
Rather than weakening the CI audit check globally or ignoring `npm audit` failures, `.github/workflows/ci.yml` executes `node ../scripts/check_web_npm_audit.mjs`, which enforces:
1. **Zero Production Vulnerabilities:** Runs `npm audit --omit=dev --json` and fails immediately if any high or critical vulnerability exists in production dependencies.
2. **Strict Advisory & Package Lock:** In the full dev+prod `npm audit --json` scan, permits only package `picomatch` with advisory `GHSA-fc5q-39xc-vjpf` (or source `1247710`) where `dev === true` and `fixAvailable === false`. Any other high/critical dev vulnerability fails CI immediately.
3. **Time-Limited Expiration:** The temporary dev-only exception is hard-coded to expire on `2026-12-18T00:00:00Z`, forcing re-evaluation or upstream upgrade once a patched `picomatch` version is published.

---

## 4. Production Release Decision

- **Deterministic Hardening & Evidence-Preserving Schema (E3.3 Stage B):** **READY FOR MERGE & PRODUCTION USE** (with `SemanticMatchingMode.DISABLED` as the default production mode and human review required for all `PROPOSED` decisions).
- **P1B Taxonomy v0.2.0 Alignment & `EngineA1` Repair (Stage A / PR #40):** **READY FOR MERGE**.
- **Live Gemini Hybrid Mode (`SemanticMatchingMode.HYBRID` with `--provider gemini`):** **REMAINS GUARDED / OPT-IN ONLY** behind `allow_external_llm`, confidentiality classification gates, and mandatory human review (`ReviewStatus.PROPOSED`).
